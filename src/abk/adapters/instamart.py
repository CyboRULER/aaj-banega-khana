"""Swiggy Instamart ordering over MCP.

The MCP server does NOT expose a one-shot "order these items" tool. The real
flow is:

    get_addresses -> search_products (per item) -> update_cart -> get_cart
    -> checkout

So this adapter works in two phases, which map onto the app's approval flow:

* ``preview(order)``  - searches each item, fills the cart, and returns a priced
  summary. Shown to the owner BEFORE they approve, so they see real prices.
* ``place(order)``    - checks out the prepared cart (Cash on Delivery).

Nothing is charged at checkout: MCP orders are COD, so money only moves at the
door.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from ..domain import GroceryOrder, OrderStatus, ProviderNotConfigured
from ..services.grocery import GroceryProvider, PlacementResult, format_list

# Swiggy rejects checkout above a cart limit; keep our own guard well under it.
DEFAULT_MAX_TOTAL = 2000.0


@dataclass
class CartLine:
    name: str
    spin_id: str
    sku_id: Optional[str]
    quantity: int
    unit_price: float
    pack: str

    @property
    def total(self) -> float:
        return self.unit_price * self.quantity


@dataclass
class PreparedCart:
    lines: list[CartLine] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return sum(line.total for line in self.lines)

    def summary(self) -> str:
        if not self.lines and self.missing:
            return "Couldn't find any of those items on Instamart: " + ", ".join(self.missing)
        out = ["Instamart cart:"]
        out += [f"- {l.quantity} x {l.name} ({l.pack}) — ₹{l.total:.0f}" for l in self.lines]
        out.append(f"Total: ₹{self.total:.0f} (cash on delivery)")
        if self.missing:
            out.append("Not found: " + ", ".join(self.missing))
        return "\n".join(out)


def _json_block(text: str) -> dict:
    """MCP tools return text; the product tools embed JSON in it."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON in MCP response")
    return json.loads(text[start:end + 1])


def pick_variant(payload: dict) -> Optional[dict]:
    """Choose the cheapest in-stock variant from a search response."""
    best = None
    for product in payload.get("data", {}).get("products", []) or []:
        for var in product.get("variations", []) or []:
            if not var.get("isInStockAndAvailable"):
                continue
            price = (var.get("price") or {}).get("offerPrice")
            if price is None:
                continue
            if best is None or price < best[0]:
                best = (price, var)
    return best[1] if best else None


class InstamartOrderer(GroceryProvider):
    name = "instamart"

    def __init__(self, mcp_url: str = "", address_id: str = "", client=None,
                 token_path: str = "", max_total: float = DEFAULT_MAX_TOTAL) -> None:
        self.mcp_url = mcp_url
        self.address_id = address_id
        self._client = client
        self.token_path = token_path
        self.max_total = max_total
        self._prepared: Optional[PreparedCart] = None

    # -- wiring ------------------------------------------------------------ #
    def _get_client(self):
        if self._client is None:
            if not self.mcp_url:
                raise ProviderNotConfigured("set ABK_INSTAMART_MCP_URL in .env")
            if not self.address_id:
                raise ProviderNotConfigured("set ABK_INSTAMART_ADDRESS_ID in .env")
            from .mcp_client import McpClient
            provider = None
            if self.token_path:
                from .instamart_auth import TokenStore
                store = TokenStore(self.token_path)
                if store.load() is None:
                    raise ProviderNotConfigured(
                        "Instamart not linked - run: python3 apps/instamart_login.py")
                provider = store.access_token
            self._client = McpClient(self.mcp_url, token_provider=provider)
        return self._client

    # -- phase 1: build a priced cart -------------------------------------- #
    def prepare(self, order: GroceryOrder) -> PreparedCart:
        client = self._get_client()
        cart = PreparedCart()
        for item in order.items:
            try:
                raw = client.call_tool("search_products",
                                       {"addressId": self.address_id, "query": item.name})
                variant = pick_variant(_json_block(raw))
            except Exception:
                variant = None
            if variant is None:
                cart.missing.append(item.name)
                continue
            cart.lines.append(CartLine(
                name=variant.get("displayName", item.name),
                spin_id=variant["spinId"],
                sku_id=variant.get("skuId"),
                quantity=max(1, int(round(item.quantity)) if item.unit in
                             ("unit", "packet", "pcs", "piece", "") else 1),
                unit_price=float((variant.get("price") or {}).get("offerPrice", 0)),
                pack=variant.get("quantityDescription", ""),
            ))
        if cart.lines:
            client.call_tool("update_cart", {
                "selectedAddressId": self.address_id,
                "items": [{"spinId": l.spin_id, "skuId": l.sku_id, "quantity": l.quantity}
                          for l in cart.lines],
            })
        self._prepared = cart
        return cart

    def preview(self, order: GroceryOrder) -> str:
        return self.prepare(order).summary()

    # -- phase 2: check out ------------------------------------------------ #
    def place(self, order: GroceryOrder) -> PlacementResult:
        if order.is_empty:
            return PlacementResult(OrderStatus.EMPTY, format_list(order), self.name)
        cart = self._prepared or self.prepare(order)
        if not cart.lines:
            return PlacementResult(
                OrderStatus.REJECTED,
                "Nothing could be added to the Instamart cart — ordering cancelled.",
                self.name)
        if cart.total > self.max_total:
            return PlacementResult(
                OrderStatus.REJECTED,
                f"Cart is ₹{cart.total:.0f}, above the ₹{self.max_total:.0f} safety limit. "
                "Order it in the Swiggy app instead — the cart is already synced.",
                self.name)
        client = self._get_client()
        reply = client.call_tool("checkout", {
            "addressId": self.address_id,
            "paymentMethod": "Cash",  # MCP orders are cash on delivery
        })
        self._prepared = None
        return PlacementResult(
            OrderStatus.PLACED,
            f"Ordered on Instamart (₹{cart.total:.0f}, cash on delivery).\n"
            + _first_lines(reply, 4),
            self.name)


def _first_lines(text: str, n: int) -> str:
    lines = [l for l in re.split(r"\n+", text.strip()) if l][:n]
    return "\n".join(lines)[:400]
