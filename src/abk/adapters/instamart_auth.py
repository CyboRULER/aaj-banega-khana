"""OAuth 2.1 (PKCE + dynamic client registration) for the Swiggy MCP servers.

Swiggy protects https://mcp.swiggy.com/im with OAuth. This module performs the
one-time browser login and stores the tokens, then refreshes them silently.

Run the login once:  python3 apps/instamart_login.py
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

AUTH_BASE = "https://mcp.swiggy.com/auth"
REGISTER_URL = f"{AUTH_BASE}/register"
AUTHORIZE_URL = f"{AUTH_BASE}/authorize"
TOKEN_URL = f"{AUTH_BASE}/token"
SCOPES = "mcp:tools mcp:resources mcp:prompts"
CALLBACK_PORT = 8765
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"


def _post(url: str, data: dict, form: bool = False) -> dict:
    if form:
        body = urllib.parse.urlencode(data).encode()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
    else:
        body = json.dumps(data).encode()
        headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


class TokenStore:
    """Persists tokens on disk and refreshes them when they expire."""

    def __init__(self, path: str) -> None:
        self.path = path

    def load(self) -> Optional[dict]:
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return None

    def save(self, data: dict) -> None:
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.chmod(self.path, 0o600)  # tokens are credentials

    def access_token(self) -> Optional[str]:
        data = self.load()
        if not data:
            return None
        token = data.get("access_token")
        if token and data.get("refresh_token"):
            try:
                return self._refresh(data)["access_token"]
            except Exception:
                return token  # keep using the current one if refresh fails
        return token

    def _refresh(self, data: dict) -> dict:
        fresh = _post(TOKEN_URL, {
            "grant_type": "refresh_token",
            "refresh_token": data["refresh_token"],
            "client_id": data.get("client_id", ""),
        }, form=True)
        merged = {**data, **fresh}
        self.save(merged)
        return merged


class _CallbackHandler(BaseHTTPRequestHandler):
    code: Optional[str] = None
    state: Optional[str] = None

    def log_message(self, *args):
        pass

    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _CallbackHandler.code = (params.get("code") or [None])[0]
        _CallbackHandler.state = (params.get("state") or [None])[0]
        body = (b"<html><body style='font-family:sans-serif;padding:40px'>"
                b"<h2>Swiggy connected.</h2><p>You can close this tab and return "
                b"to the terminal.</p></body></html>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def login(store: TokenStore, open_browser: bool = True) -> dict:
    """Run the one-time OAuth login and persist the tokens."""
    client = _post(REGISTER_URL, {
        "client_name": "Aaj Banega Khana",
        "redirect_uris": [REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": SCOPES,
    })
    client_id = client["client_id"]
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(16)

    url = AUTHORIZE_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": REDIRECT_URI,
        "response_type": "code", "scope": SCOPES, "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })

    server = HTTPServer(("localhost", CALLBACK_PORT), _CallbackHandler)
    threading.Thread(target=server.handle_request, daemon=True).start()

    print("\nOpen this URL and log in with the Swiggy account you order from:\n")
    print(url + "\n")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    print("Waiting for the redirect back to localhost...")
    for _ in range(600):  # up to ~5 minutes
        if _CallbackHandler.code:
            break
        import time
        time.sleep(0.5)
    if not _CallbackHandler.code:
        raise TimeoutError("no authorization code received - login timed out")
    if _CallbackHandler.state != state:
        raise ValueError("state mismatch - aborting for safety")

    tokens = _post(TOKEN_URL, {
        "grant_type": "authorization_code",
        "code": _CallbackHandler.code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "code_verifier": verifier,
    }, form=True)
    tokens["client_id"] = client_id
    store.save(tokens)
    return tokens
