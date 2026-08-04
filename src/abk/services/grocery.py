"""Grocery providers behind a single `GroceryProvider` port.

- ManualListAdapter (default): produces a tidy shopping list for the owner to
  order in one tap. Always reliable.
- InstamartOrderer (adapters/instamart.py): places real orders over Swiggy's
  MCP server. Selected when ABK_GROCERY_PROVIDER=instamart.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..domain import GroceryOrder, OrderStatus, ProviderNotConfigured


@dataclass
class PlacementResult:
    status: OrderStatus
    message: str
    provider: str


def format_list(order: GroceryOrder) -> str:
    if order.is_empty:
        return "Everything is already at home — nothing to order."
    lines = [f"- {i.quantity:g} {i.unit} {i.name}" for i in order.items]
    return "Grocery list:\n" + "\n".join(lines)


class GroceryProvider(ABC):
    name: str = "base"

    @abstractmethod
    def place(self, order: GroceryOrder) -> PlacementResult: ...

    def preview(self, order: GroceryOrder) -> str:
        """What the owner sees before approving. Providers that can price the
        basket (e.g. Instamart) override this to show real prices."""
        return format_list(order)


class ManualListAdapter(GroceryProvider):
    name = "manual"

    def place(self, order: GroceryOrder) -> PlacementResult:
        if order.is_empty:
            return PlacementResult(OrderStatus.EMPTY, format_list(order), self.name)
        msg = (format_list(order) +
               "\n\nTap to order in your Blinkit/Instamart app. ✅ when done.")
        return PlacementResult(OrderStatus.PLACED, msg, self.name)


def build_provider(settings) -> GroceryProvider:
    choice = (getattr(settings, "grocery_provider", "manual") or "manual").lower()
    if choice == "instamart":
        from ..adapters.instamart import InstamartOrderer
        return InstamartOrderer(
            mcp_url=getattr(settings, "instamart_mcp_url", ""),
            address_id=getattr(settings, "instamart_address_id", ""),
            token_path=getattr(settings, "instamart_token_path", ""))
    return ManualListAdapter()
