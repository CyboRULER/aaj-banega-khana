"""Health check - verifies every moving part end to end.

Run:  python3 apps/status.py
Prints PASS/FAIL for each component so you can tell at a glance whether the
system is working.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from abk.config import Settings, load_env_file  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
OK, BAD, WARN = "  PASS", "  FAIL", "  WARN"
results: list[bool] = []


def report(status: str, label: str, detail: str = "") -> None:
    results.append(status == OK)
    print(f"{status}  {label}" + (f"  ({detail})" if detail else ""))


def get(url: str, timeout: int = 5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def main() -> None:
    load_env_file(os.path.join(ROOT, ".env"))
    s = Settings.from_env()
    print("\nAaj Banega Khana - system status\n" + "-" * 46)

    # 1. WhatsApp gateway
    try:
        h = get(s.gateway_url.rstrip("/") + "/health")
        if h.get("connected") and h.get("group"):
            report(OK, "whatsapp gateway", f"group {h['group'][:22]}...")
        elif h.get("connected"):
            report(WARN, "whatsapp gateway", "connected but NO group selected")
        else:
            report(BAD, "whatsapp gateway", "not connected - scan the QR")
    except Exception as e:
        report(BAD, "whatsapp gateway", f"unreachable: {type(e).__name__}")

    # 2. Role mapping (can the agent tell owner from cook?)
    try:
        p = get(s.gateway_url.rstrip("/") + "/participants")
        mapped = set(p.get("lidToPhone", {}).values())
        known = {s.owner_jid, s.cook_jid}
        missing = known - mapped
        if not missing:
            report(OK, "role mapping", "owner + cook both recognised")
        else:
            report(WARN, "role mapping", f"not in group: {', '.join(missing)}")
    except Exception:
        report(WARN, "role mapping", "gateway has no /participants (restart it)")

    # 3. Core server
    try:
        req = urllib.request.Request(
            "http://localhost:8000/inbound",
            data=json.dumps({"jid": "healthcheck@none", "text": "ping"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        body = json.loads(urllib.request.urlopen(req, timeout=10).read())
        report(OK, "core server", f"responding ({body.get('action', '?')})")
    except Exception as e:
        report(BAD, "core server", f"not running: {type(e).__name__}")

    # 4. LLM
    provider = s.resolve_provider()
    if provider == "offline":
        report(WARN, "llm", "offline rule engine (no API key set)")
    else:
        try:
            from abk.llm import build_llm
            from abk.domain import Intent, Role
            got = build_llm(s).classify("approve", Role.OWNER)
            if got == Intent.APPROVE:
                report(OK, "llm", f"{provider} responding correctly")
            else:
                report(WARN, "llm", f"{provider} replied {got.value} for 'approve'")
        except Exception as e:
            report(BAD, "llm", f"{provider} error: {type(e).__name__}")

    # 5. Storage
    try:
        from abk.services.db import connect
        conn = connect(os.path.join(ROOT, s.db_path))
        n = conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
        report(OK if n else WARN, "recipe storage", f"{n} recipe(s)")
    except Exception as e:
        report(BAD, "recipe storage", f"{type(e).__name__}")

    # 6. Config sanity
    if s.owner_jid == s.cook_jid:
        report(BAD, "roles", "owner and cook are the same number")
    else:
        report(OK, "roles", f"owner {s.owner_jid.split('@')[0]} / "
                            f"cook {s.cook_jid.split('@')[0]}")

    # 7. Ordering
    if s.grocery_provider == "instamart" and not s.instamart_mcp_url:
        report(WARN, "ordering", "instamart selected, no MCP url - manual list used")
    else:
        report(OK, "ordering", s.grocery_provider)

    print("-" * 46)
    passed, total = sum(results), len(results)
    print(f"{passed}/{total} checks passed. "
          f"Daily plan at {s.plan_time} {s.timezone}.\n")


if __name__ == "__main__":
    main()
