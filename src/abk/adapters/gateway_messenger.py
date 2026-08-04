"""Live Messenger that posts to the Node/Baileys WhatsApp gateway over HTTP.

Uses only the stdlib (urllib) so it adds no dependency.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Optional

from ..config import Settings
from ..domain import Role
from ..services.messaging import Messenger


class GatewayMessenger(Messenger):
    def __init__(self, settings: Settings) -> None:
        self.url = settings.gateway_url.rstrip("/") + "/send"
        self.group_id = settings.group_id
        self.mentions = {Role.OWNER: settings.owner_jid, Role.COOK: settings.cook_jid}

    def send(self, text: str, to: Optional[Role] = None) -> None:
        # group_id None -> the gateway uses the group it resolved from ABK_GROUP_NAME.
        payload = {
            "group_id": self.group_id or None,
            "text": text,
            "mention": self.mentions.get(to) if to else None,
        }
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=10)  # pragma: no cover - live path
