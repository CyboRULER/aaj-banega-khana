"""Minimal MCP (Model Context Protocol) client over streamable HTTP.

MCP is JSON-RPC 2.0 over HTTP POST. This client implements just what the Order
Agent needs: initialize -> tools/list -> tools/call. Stdlib only (urllib).

Used by InstamartMCPAdapter. Works as soon as ABK_INSTAMART_MCP_URL is set;
until then nothing calls it.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any, Callable, Optional

PROTOCOL_VERSION = "2025-06-18"


class McpError(Exception):
    """An MCP server returned an error or an unusable response."""


class McpClient:
    def __init__(self, url: str, headers: Optional[dict] = None,
                 transport: Optional[Callable[[dict], dict]] = None,
                 token_provider: Optional[Callable[[], Optional[str]]] = None) -> None:
        self.url = url
        self.headers = headers or {}
        self.token_provider = token_provider
        self._transport = transport or self._http
        self._id = 0
        self._session_id: Optional[str] = None
        self._initialized = False

    # -- transport --------------------------------------------------------- #
    def _http(self, payload: dict) -> dict:  # pragma: no cover - network path
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self.headers,
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        if self.token_provider and "Authorization" not in headers:
            token = self.token_provider()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode("utf-8"),
            headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                self._session_id = sid
            body = resp.read().decode("utf-8").strip()
        return _parse_body(body)

    def _rpc(self, method: str, params: Optional[dict] = None) -> Any:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method,
                   "params": params or {}}
        data = self._transport(payload)
        if not isinstance(data, dict):
            raise McpError(f"unexpected response for {method}: {data!r}")
        if "error" in data:
            raise McpError(f"{method} failed: {data['error']}")
        return data.get("result", {})

    # -- MCP surface ------------------------------------------------------- #
    def initialize(self) -> dict:
        result = self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "aaj-banega-khana", "version": "0.1.0"},
        })
        self._initialized = True
        return result

    def ensure_ready(self) -> None:
        if not self._initialized:
            self.initialize()

    def list_tools(self) -> list[dict]:
        self.ensure_ready()
        return self._rpc("tools/list").get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> str:
        """Call a tool and return its text content joined into one string."""
        self.ensure_ready()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise McpError(f"tool {name} returned an error: {result}")
        return _content_text(result)


def _parse_body(body: str) -> dict:
    """Accept either a plain JSON body or an SSE 'data:' framed body."""
    if not body:
        raise McpError("empty response from MCP server")
    if body.startswith("{"):
        return json.loads(body)
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            chunk = line[5:].strip()
            if chunk and chunk != "[DONE]":
                return json.loads(chunk)
    raise McpError(f"could not parse MCP response: {body[:200]}")


def _content_text(result: dict) -> str:
    parts = [c.get("text", "") for c in result.get("content", [])
             if c.get("type") == "text"]
    return "\n".join(p for p in parts if p).strip() or json.dumps(result)
