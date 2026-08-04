"""Runtime configuration, loaded from environment variables.

Kept dependency-free (no pydantic) so the core runs with only the stdlib.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def load_env_file(path: str = ".env") -> None:
    """Minimal .env loader (stdlib). Sets vars that aren't already in the env."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


@dataclass
class Settings:
    owner_jid: str = "owner@s.whatsapp.net"
    cook_jid: str = "cook@s.whatsapp.net"
    # WhatsApp may address group members by LID instead of phone JID.
    owner_lid: str = ""
    cook_lid: str = ""
    group_id: str = ""
    group_name: str = ""
    timezone: str = "Asia/Kolkata"
    plan_time: str = "08:00"

    # LLM provider: auto | anthropic | xai | offline
    llm_provider: str = "auto"
    anthropic_api_key: str = ""
    planner_model: str = "claude-opus-4-8"
    extractor_model: str = "claude-sonnet-4-6"

    xai_api_key: str = ""
    xai_base_url: str = "https://api.x.ai/v1"
    xai_model: str = "grok-4.5"

    grocery_provider: str = "manual"
    instamart_mcp_url: str = ""
    instamart_token_path: str = "data/instamart_token.json"
    instamart_address_id: str = ""

    gateway_url: str = "http://localhost:8787"

    db_path: str = "data/abk.sqlite3"
    recipe_dir: str = "recipes"

    def today(self) -> str:
        """Today's date in the configured timezone (falls back to local time)."""
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(self.timezone)).strftime("%Y-%m-%d")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d")

    def resolve_provider(self) -> str:
        """Which LLM backend to use given keys + explicit choice."""
        choice = (self.llm_provider or "auto").lower()
        if choice in ("anthropic", "xai", "offline"):
            return choice
        if self.xai_api_key:
            return "xai"
        if self.anthropic_api_key:
            return "anthropic"
        return "offline"

    @property
    def use_real_llm(self) -> bool:
        return self.resolve_provider() in ("anthropic", "xai")

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Settings":
        e = env if env is not None else os.environ
        d = cls()
        return cls(
            owner_jid=e.get("ABK_OWNER_JID", d.owner_jid),
            cook_jid=e.get("ABK_COOK_JID", d.cook_jid),
            owner_lid=e.get("ABK_OWNER_LID", d.owner_lid),
            cook_lid=e.get("ABK_COOK_LID", d.cook_lid),
            group_id=e.get("ABK_GROUP_ID", d.group_id),
            group_name=e.get("ABK_GROUP_NAME", d.group_name),
            timezone=e.get("ABK_TIMEZONE", d.timezone),
            plan_time=e.get("ABK_PLAN_TIME", d.plan_time),
            llm_provider=e.get("ABK_LLM_PROVIDER", d.llm_provider),
            anthropic_api_key=e.get("ANTHROPIC_API_KEY", d.anthropic_api_key),
            planner_model=e.get("ABK_PLANNER_MODEL", d.planner_model),
            extractor_model=e.get("ABK_EXTRACTOR_MODEL", d.extractor_model),
            xai_api_key=e.get("ABK_XAI_API_KEY", d.xai_api_key),
            xai_base_url=e.get("ABK_XAI_BASE_URL", d.xai_base_url),
            xai_model=e.get("ABK_XAI_MODEL", d.xai_model),
            grocery_provider=e.get("ABK_GROCERY_PROVIDER", d.grocery_provider),
            instamart_mcp_url=e.get("ABK_INSTAMART_MCP_URL", d.instamart_mcp_url),
            instamart_token_path=e.get("ABK_INSTAMART_TOKEN_PATH", d.instamart_token_path),
            instamart_address_id=e.get("ABK_INSTAMART_ADDRESS_ID", d.instamart_address_id),
            gateway_url=e.get("ABK_GATEWAY_URL", d.gateway_url),
            db_path=e.get("ABK_DB_PATH", d.db_path),
            recipe_dir=e.get("ABK_RECIPE_DIR", d.recipe_dir),
        )
