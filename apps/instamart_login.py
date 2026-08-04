"""One-time Swiggy Instamart login, so the agent can place real orders.

Run:  python3 apps/instamart_login.py
      python3 apps/instamart_login.py --check    # show status / list tools
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from abk.adapters.instamart_auth import TokenStore, login  # noqa: E402
from abk.config import Settings, load_env_file  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def main() -> None:
    load_env_file(os.path.join(ROOT, ".env"))
    s = Settings.from_env()
    path = os.path.join(ROOT, s.instamart_token_path)
    store = TokenStore(path)
    url = s.instamart_mcp_url or "https://mcp.swiggy.com/im"

    if "--check" in sys.argv:
        data = store.load()
        if not data:
            print("\nNot linked yet. Run: python3 apps/instamart_login.py\n")
            return
        print(f"\nLinked. Token stored at {path}")
        try:
            from abk.adapters.mcp_client import McpClient
            client = McpClient(url, token_provider=store.access_token)
            tools = client.list_tools()
            print(f"Instamart MCP exposes {len(tools)} tool(s):")
            for t in tools:
                print(f"  - {t.get('name')}: {str(t.get('description', ''))[:70]}")
        except Exception as e:
            print(f"Could not reach the MCP server: {type(e).__name__}: {str(e)[:160]}")
        print()
        return

    print(f"\nLinking Swiggy Instamart ({url})")
    print("A browser window will open - log in with the Swiggy account you order from.")
    try:
        login(store)
    except Exception as e:
        print(f"\nLogin failed: {type(e).__name__}: {str(e)[:200]}\n")
        return
    print(f"\nLinked. Tokens saved to {path}")
    print("Set ABK_INSTAMART_MCP_URL=https://mcp.swiggy.com/im in .env, then")
    print("restart the core:  python3 apps/server.py\n")


if __name__ == "__main__":
    main()
