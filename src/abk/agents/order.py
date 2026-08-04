"""Order Agent: cook's material list -> owner approval -> place order.

No inventory logic: the cook decides what's needed and sends the list; the owner
approves; the order is placed through the configured provider.
"""
from __future__ import annotations

from ..domain import GroceryItem, GroceryOrder, OrderStatus, ProviderNotConfigured, Role
from ..services.grocery import (
    GroceryProvider, ManualListAdapter, PlacementResult, format_list,
)
from ..services.messaging import Messenger


def _merge(items: list[GroceryItem]) -> list[GroceryItem]:
    merged: dict[tuple[str, str], GroceryItem] = {}
    order: list[tuple[str, str]] = []
    for it in items:
        k = (it.name.strip().lower(), it.unit.strip().lower())
        if k in merged:
            prev = merged[k]
            merged[k] = GroceryItem(prev.name, prev.quantity + it.quantity, prev.unit)
        else:
            merged[k] = it
            order.append(k)
    return [merged[k] for k in order]


class OrderAgent:
    def __init__(self, provider: GroceryProvider, messenger: Messenger) -> None:
        self.provider = provider
        self.messenger = messenger

    def build_order(self, items: list[GroceryItem]) -> GroceryOrder:
        """Turn the cook's list into an order and ask the owner to approve."""
        merged = _merge(items)
        status = OrderStatus.EMPTY if not merged else OrderStatus.PENDING
        order = GroceryOrder(items=merged, status=status, provider=self.provider.name)
        if order.is_empty:
            self.messenger.send(
                "The cook's list looked empty — nothing to order.", to=Role.OWNER)
            return order
        try:
            body = self.provider.preview(order)
        except ProviderNotConfigured:
            body = format_list(order)  # fall back to a plain list
        self.messenger.send("Cook needs these:\n" + body + "\n\nApprove to order?",
                            to=Role.OWNER)
        return order

    def place(self, order: GroceryOrder) -> PlacementResult:
        try:
            result = self.provider.place(order)
        except ProviderNotConfigured:
            # e.g. Instamart selected but MCP not wired yet -> safe manual fallback.
            result = ManualListAdapter().place(order)
        order.status = result.status
        order.provider = result.provider
        self.messenger.send(result.message, to=Role.OWNER)
        return result
