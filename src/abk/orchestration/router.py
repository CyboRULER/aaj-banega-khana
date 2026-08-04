"""Inbound message router: role resolution -> intent -> authority -> dispatch."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..config import Settings
from ..domain import Intent, Role
from ..llm import LLMClient, find_url
from ..logging_setup import get_logger
from ..services.messaging import Messenger
from .conversation import Conversation

# Only the owner may authorise: approve/reject a plan or an order, or change one.
# Adding a recipe is harmless (no spending, no authorisation) so either person
# in the group can share a recipe link.
_OWNER_ONLY = {Intent.APPROVE, Intent.REJECT, Intent.REVISE}


@dataclass
class RouterResult:
    role: Role
    intent: Optional[Intent]
    action: str


class MessageRouter:
    def __init__(self, settings: Settings, llm: LLMClient,
                 conversation: Conversation, messenger: Messenger) -> None:
        self.settings = settings
        self.llm = llm
        self.conversation = conversation
        self.messenger = messenger
        self.log = get_logger("abk.router")

    def resolve_role(self, jid: str, lid: str = "") -> Role:
        """Match against the phone JID or the WhatsApp LID (either may arrive)."""
        ids = {i for i in (jid, lid) if i}
        owner_ids = {i for i in (self.settings.owner_jid, self.settings.owner_lid) if i}
        cook_ids = {i for i in (self.settings.cook_jid, self.settings.cook_lid) if i}
        if ids & owner_ids:
            return Role.OWNER
        if ids & cook_ids:
            return Role.COOK
        return Role.UNKNOWN

    def handle_inbound(self, jid: str, text: str, lid: str = "") -> RouterResult:
        role = self.resolve_role(jid, lid)
        if role == Role.UNKNOWN:
            self.log.info("ignoring message from unknown sender %s (lid %s)", jid, lid or "-")
            return RouterResult(role, None, "ignored_unknown_sender")

        intent = self.llm.classify(text, role)
        self.log.info("inbound role=%s intent=%s text=%r", role.value, intent.value, text[:60])

        # Authority guardrail: only the owner may approve/reject/revise.
        if intent in _OWNER_ONLY and role != Role.OWNER:
            self.log.info("blocked %s from non-owner %s", intent.value, role.value)
            # Tell them why, instead of silently doing nothing.
            self.messenger.send(
                "Only the owner can approve or change the meal plan. "
                "Ask them to reply here.", to=role)
            return RouterResult(role, intent, "ignored_unauthorized")

        if intent == Intent.APPROVE:
            return RouterResult(role, intent, self.conversation.on_approve())
        if intent == Intent.REJECT:
            return RouterResult(role, intent, self.conversation.on_reject())
        if intent == Intent.REVISE:
            return RouterResult(role, intent, self.conversation.on_revise(text))
        if intent == Intent.ADD_RECIPE:
            url = find_url(text)
            if not url:
                return RouterResult(role, intent, "noop")
            self.conversation.on_add_recipe(url)
            return RouterResult(role, intent, "recipe_added")
        if intent == Intent.GROCERY_LIST:
            return RouterResult(role, intent, self.conversation.on_grocery_list(text))
        if intent == Intent.COOK_FEEDBACK:
            return RouterResult(role, intent, self.conversation.on_cook_feedback(text))
        if intent == Intent.QUERY:
            return RouterResult(role, intent,
                                self.conversation.on_query(self.settings.today()))
        return RouterResult(role, intent, "noop")
