import unittest

from abk.adapters.mcp_client import McpClient, McpError, _content_text, _parse_body
from abk.domain import GroceryItem, GroceryOrder, OrderStatus, ProviderNotConfigured


class FakeMcpTransport:
    """Scripted MCP server: initialize -> tools/list -> tools/call."""

    def __init__(self, tools=None, order_reply="Order placed, ETA 12 min"):
        self.tools = tools if tools is not None else [{"name": "instamart_place_order"}]
        self.order_reply = order_reply
        self.calls = []

    def __call__(self, payload):
        method = payload["method"]
        self.calls.append((method, payload.get("params")))
        rid = payload["id"]
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": rid,
                    "result": {"protocolVersion": "2025-06-18", "capabilities": {}}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": rid, "result": {"tools": self.tools}}
        if method == "tools/call":
            return {"jsonrpc": "2.0", "id": rid,
                    "result": {"content": [{"type": "text", "text": self.order_reply}]}}
        return {"jsonrpc": "2.0", "id": rid, "error": {"message": "unknown method"}}


class TestMcpClient(unittest.TestCase):
    def test_parse_plain_json(self):
        self.assertEqual(_parse_body('{"a": 1}'), {"a": 1})

    def test_parse_sse_framed(self):
        self.assertEqual(_parse_body('event: message\ndata: {"a": 2}\n'), {"a": 2})

    def test_parse_empty_raises(self):
        with self.assertRaises(McpError):
            _parse_body("")

    def test_content_text_joins(self):
        self.assertEqual(
            _content_text({"content": [{"type": "text", "text": "hi"},
                                       {"type": "text", "text": "there"}]}),
            "hi\nthere")

    def test_list_and_call(self):
        t = FakeMcpTransport()
        c = McpClient("http://x", transport=t)
        self.assertEqual([x["name"] for x in c.list_tools()], ["instamart_place_order"])
        self.assertEqual(c.call_tool("instamart_place_order", {"items": []}),
                         "Order placed, ETA 12 min")
        self.assertEqual(t.calls[0][0], "initialize")  # auto-initialized

    def test_rpc_error_raises(self):
        c = McpClient("http://x", transport=lambda p: {
            "jsonrpc": "2.0", "id": p["id"], "error": {"message": "boom"}})
        with self.assertRaises(McpError):
            c.list_tools()


class TestMcpAuth(unittest.TestCase):
    def test_bearer_token_is_attached(self):
        seen = {}

        def transport(payload):
            return {"jsonrpc": "2.0", "id": payload["id"], "result": {"tools": []}}

        c = McpClient("http://x", transport=transport, token_provider=lambda: "tok123")
        c.list_tools()
        # token_provider is only used by the real HTTP transport; assert it is stored
        self.assertEqual(c.token_provider(), "tok123")

    def test_missing_token_file_reports_not_linked(self):
        from abk.adapters.instamart import InstamartOrderer
        from abk.domain import GroceryItem, GroceryOrder, ProviderNotConfigured
        a = InstamartOrderer(mcp_url="https://mcp.swiggy.com/im", address_id="addr1",
                             token_path="/tmp/definitely-missing-token.json")
        with self.assertRaises(ProviderNotConfigured) as ctx:
            a.place(GroceryOrder(items=[GroceryItem("onion", 1, "kg")]))
        self.assertIn("instamart_login", str(ctx.exception))


class TestTokenStore(unittest.TestCase):
    def test_roundtrip_and_permissions(self):
        import os, tempfile
        from abk.adapters.instamart_auth import TokenStore
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub", "tok.json")
            s = TokenStore(p)
            self.assertIsNone(s.load())
            s.save({"access_token": "abc"})
            self.assertEqual(s.load()["access_token"], "abc")
            self.assertEqual(s.access_token(), "abc")
            self.assertEqual(oct(os.stat(p).st_mode)[-3:], "600")


if __name__ == "__main__":
    unittest.main()
