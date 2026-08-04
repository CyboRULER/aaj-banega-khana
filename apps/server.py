"""Production entrypoint: webhook server + daily scheduler.

Receives inbound messages from the Node gateway at POST /inbound and drives the
router. A background thread triggers the daily plan at ABK_PLAN_TIME. Uses live
adapters when configured, otherwise the offline engine.

Run:  python apps/server.py
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from abk.app import build_app  # noqa: E402
from abk.config import Settings  # noqa: E402
from abk.logging_setup import get_logger  # noqa: E402
from abk.services.messaging import Messenger  # noqa: E402

log = get_logger("abk.server")


def _live_messenger(settings: Settings) -> Messenger | None:
    # Use the WhatsApp gateway if a group name or id is configured.
    if settings.group_id or settings.group_name:
        from abk.adapters.gateway_messenger import GatewayMessenger
        return GatewayMessenger(settings)
    return None


def _live_transcriber(settings: Settings):
    from abk.adapters.youtube import YouTubeTranscriber
    return YouTubeTranscriber()


def build_live_app():
    from abk.config import load_env_file
    load_env_file(os.path.join(os.path.dirname(__file__), "..", ".env"))
    settings = Settings.from_env()
    kwargs = {}
    msgr = _live_messenger(settings)
    if msgr is not None:
        kwargs["messenger"] = msgr
    try:
        kwargs["transcriber"] = _live_transcriber(settings)
    except Exception:  # youtube api not installed
        pass
    app = build_app(settings, persist=True, **kwargs)

    # Load profile + seed recipes from config/ if present.
    root = os.path.join(os.path.dirname(__file__), "..")
    from abk.services.seed import apply_seeds
    apply_seeds(app, os.path.join(root, "config", "profile.json"),
                os.path.join(root, "config", "recipes.json"))
    return app


def _tz(name: str):
    """Resolve a timezone, falling back to local time if unavailable."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        log.warning("unknown timezone %r - using system local time", name)
        return None


def _scheduler_loop(app) -> None:
    plan_time = app.settings.plan_time
    tz = _tz(app.settings.timezone)
    fired_on = None
    while True:
        now_dt = datetime.now(tz) if tz else datetime.now()
        now = now_dt.strftime("%H:%M")
        today = now_dt.strftime("%Y-%m-%d")
        if now == plan_time and fired_on != today:
            fired_on = today
            log.info("firing daily plan for %s", today)
            try:
                app.conversation.start_daily(today)
            except Exception as exc:  # keep the loop alive
                log.error("daily plan failed: %s", exc)
        time.sleep(20)


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # silence default logging
            pass

        def _json(self, payload, status=200):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            # Hosted platforms poll a health endpoint to decide if the deploy is up.
            if self.path.rstrip("/") in ("/health", ""):
                self._json({"ok": True, "plan_time": app.settings.plan_time})
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path != "/inbound":
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or "{}")
            try:
                result = app.inbound(body.get("jid", ""), body.get("text", ""),
                                     body.get("lid", ""))
                payload = {"role": result.role.value, "action": result.action}
            except Exception as exc:  # never let one bad message kill the server
                log.error("inbound failed: %s", exc)
                payload = {"error": str(exc)}
            self._json(payload)

    return Handler


def _make_server(host: str, port: int, handler) -> ThreadingHTTPServer:
    """Bind the HTTP server, using IPv6 when the host is an IPv6 address.

    Railway's private network resolves *.railway.internal to IPv6 only, so the
    core must bind '::' there or the gateway cannot reach it. Binding '::' is
    dual-stack on Linux, so IPv4 callers still work.
    """
    if ":" in host:
        class _V6(ThreadingHTTPServer):
            address_family = socket.AF_INET6
        return _V6((host, port), handler)
    return ThreadingHTTPServer((host, port), handler)


def main() -> None:
    app = build_live_app()
    threading.Thread(target=_scheduler_loop, args=(app,), daemon=True).start()
    # Hosted platforms inject PORT; ABK_SERVER_PORT still wins for local runs.
    port = int(os.environ.get("ABK_SERVER_PORT") or os.environ.get("PORT") or "8000")
    host = os.environ.get("ABK_BIND_HOST", "0.0.0.0")
    server = _make_server(host, port, make_handler(app))
    log.info("ABK core listening on [%s]:%d (plan time %s)", host, port,
             app.settings.plan_time)
    server.serve_forever()


if __name__ == "__main__":
    main()
