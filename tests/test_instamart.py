import unittest

from abk.adapters.instamart import (
    CartLine, InstamartOrderer, PreparedCart, pick_variant,
)
from abk.domain import GroceryItem, GroceryOrder, OrderStatus, ProviderNotConfigured


def variant(spin, price, name, stock=True, pack="1 kg"):
    return {"spinId": spin, "skuId": "SKU" + spin, "displayName": name,
            "quantityDescription": pack, "price": {"offerPrice": price},
            "isInStockAndAvailable": stock}


def search_payload(variants):
    return '{"success": true, "data": {"products": [{"variations": %s}]}}' % (
        str(variants).replace("'", '"').replace("True", "true").replace("False", "false"))


class FakeClient:
    """Scripted Instamart MCP: search -> update_cart -> checkout."""

    def __init__(self, results=None, checkout_reply="Order ABC123 placed. ETA 12 mins."):
        self.results = results or {}
        self.checkout_reply = checkout_reply
        self.calls = []

    def call_tool(self, name, args):
        self.calls.append((name, args))
        if name == "search_products":
            return self.results.get(args["query"], search_payload([]))
        if name == "update_cart":
            return "Cart updated"
        if name == "checkout":
            return self.checkout_reply
        return "{}"


class TestPickVariant(unittest.TestCase):
    def test_picks_cheapest_in_stock(self):
        payload = {"data": {"products": [{"variations": [
            variant("A", 90, "Onion 2kg"), variant("B", 38, "Onion 1kg"),
        ]}]}}
        self.assertEqual(pick_variant(payload)["spinId"], "B")

    def test_skips_out_of_stock(self):
        payload = {"data": {"products": [{"variations": [
            variant("A", 10, "Cheap but gone", stock=False), variant("B", 38, "Onion"),
        ]}]}}
        self.assertEqual(pick_variant(payload)["spinId"], "B")

    def test_none_when_nothing_available(self):
        self.assertIsNone(pick_variant({"data": {"products": []}}))


class TestPreparedCart(unittest.TestCase):
    def test_total_and_summary(self):
        c = PreparedCart([CartLine("Onion", "S1", None, 2, 38.0, "1 kg")], ["saffron"])
        self.assertEqual(c.total, 76.0)
        s = c.summary()
        self.assertIn("Onion", s)
        self.assertIn("76", s)
        self.assertIn("saffron", s)   # missing items are surfaced

    def test_all_missing_message(self):
        self.assertIn("Couldn't find", PreparedCart([], ["x"]).summary())


class TestOrderFlow(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient({
            "onion": search_payload([variant("S1", 38, "Onion (Pyaaz)")]),
            "bread": search_payload([variant("S2", 25, "Brown Bread", pack="400 g")]),
        })
        self.o = InstamartOrderer(mcp_url="u", address_id="addr1", client=self.client)
        self.order = GroceryOrder(items=[GroceryItem("onion", 1, "kg"),
                                         GroceryItem("bread", 2, "packet")])

    def test_preview_prices_the_basket(self):
        text = self.o.preview(self.order)
        self.assertIn("Onion (Pyaaz)", text)
        self.assertIn("cash on delivery", text)
        tools = [c[0] for c in self.client.calls]
        self.assertEqual(tools.count("search_products"), 2)
        self.assertIn("update_cart", tools)
        self.assertNotIn("checkout", tools)  # preview must NOT order

    def test_cart_uses_spin_ids(self):
        self.o.preview(self.order)
        cart = [c for c in self.client.calls if c[0] == "update_cart"][0][1]
        self.assertEqual(cart["selectedAddressId"], "addr1")
        self.assertEqual({i["spinId"] for i in cart["items"]}, {"S1", "S2"})

    def test_place_checks_out_with_cod(self):
        self.o.preview(self.order)
        res = self.o.place(self.order)
        self.assertEqual(res.status, OrderStatus.PLACED)
        args = [c for c in self.client.calls if c[0] == "checkout"][0][1]
        self.assertEqual(args["paymentMethod"], "Cash")
        self.assertEqual(args["addressId"], "addr1")

    def test_missing_items_are_reported_not_silent(self):
        text = self.o.preview(GroceryOrder(items=[GroceryItem("dragonfruit", 1, "unit")]))
        self.assertIn("dragonfruit", text)

    def test_refuses_when_nothing_found(self):
        res = self.o.place(GroceryOrder(items=[GroceryItem("dragonfruit", 1, "unit")]))
        self.assertEqual(res.status, OrderStatus.REJECTED)
        self.assertNotIn("checkout", [c[0] for c in self.client.calls])

    def test_spend_limit_blocks_large_carts(self):
        o = InstamartOrderer(mcp_url="u", address_id="a", client=self.client, max_total=10)
        res = o.place(self.order)
        self.assertEqual(res.status, OrderStatus.REJECTED)
        self.assertIn("safety limit", res.message)
        self.assertNotIn("checkout", [c[0] for c in self.client.calls])

    def test_requires_address(self):
        with self.assertRaises(ProviderNotConfigured):
            InstamartOrderer(mcp_url="u").place(self.order)


if __name__ == "__main__":
    unittest.main()
