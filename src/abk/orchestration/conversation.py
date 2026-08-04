"""Conversation state machine.

Flow: Diet Agent proposes a plan -> owner approves/revises. On approval the cook
is notified and asked for the material list. The cook sends the list -> owner
approves -> the order is placed. A late 'approve' resolves whichever decision is
pending (plan, then order).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..agents.adder import AdderAgent
from ..agents.cook import notify_cook
from ..agents.diet import DietAgent
from ..agents.order import OrderAgent
from ..domain import GroceryOrder, MealPlan, NoRecipesError, OrderStatus, PlanStatus, Role
from ..llm import LLMClient
from ..services.messaging import Messenger


class Awaiting(str, Enum):
    IDLE = "idle"
    PLAN_APPROVAL = "plan_approval"
    ORDER_APPROVAL = "order_approval"


@dataclass
class ConversationState:
    awaiting: Awaiting = Awaiting.IDLE
    plan: Optional[MealPlan] = None
    order: Optional[GroceryOrder] = None


class Conversation:
    def __init__(self, diet: DietAgent, order_agent: OrderAgent, adder: AdderAgent,
                 messenger: Messenger, llm: LLMClient) -> None:
        self.diet = diet
        self.order_agent = order_agent
        self.adder = adder
        self.messenger = messenger
        self.llm = llm
        self.state = ConversationState()

    # -- daily trigger ----------------------------------------------------- #
    def start_daily(self, date: str) -> Optional[MealPlan]:
        try:
            plan = self.diet.propose(date)
        except NoRecipesError:
            self.messenger.send(
                "Recipe book is empty — share a few recipe links first.", to=Role.OWNER)
            self.state = ConversationState()
            return None
        self.state = ConversationState(awaiting=Awaiting.PLAN_APPROVAL, plan=plan)
        return plan

    # -- owner decisions --------------------------------------------------- #
    def on_approve(self) -> str:
        if self.state.awaiting == Awaiting.PLAN_APPROVAL and self.state.plan:
            self.state.plan.status = PlanStatus.APPROVED
            notify_cook(self.state.plan, self.messenger)  # menu + "send material list"
            self.state.awaiting = Awaiting.IDLE
            return "plan_approved"
        if self.state.awaiting == Awaiting.ORDER_APPROVAL and self.state.order:
            self.order_agent.place(self.state.order)
            self.state.awaiting = Awaiting.IDLE
            return "order_placed"
        self.messenger.send("Nothing is pending approval right now.", to=Role.OWNER)
        return "noop"

    def on_reject(self) -> str:
        if self.state.awaiting == Awaiting.PLAN_APPROVAL and self.state.plan:
            self.state.plan.status = PlanStatus.REJECTED
            self.state.awaiting = Awaiting.IDLE
            self.messenger.send(
                "Plan cancelled. Tell me what you'd like instead.", to=Role.OWNER)
            return "plan_rejected"
        if self.state.awaiting == Awaiting.ORDER_APPROVAL and self.state.order:
            self.state.order.status = OrderStatus.REJECTED
            self.state.awaiting = Awaiting.IDLE
            self.messenger.send("Grocery order cancelled.", to=Role.OWNER)
            return "order_rejected"
        self.messenger.send("Nothing is pending right now.", to=Role.OWNER)
        return "noop"

    def on_revise(self, note: str) -> str:
        if self.state.awaiting == Awaiting.PLAN_APPROVAL and self.state.plan:
            before = [m.recipe.id for m in self.state.plan.meals]
            plan = self.diet.propose(
                date=self.state.plan.date, feedback=note,
                revision=self.state.plan.revision + 1)
            self.state.plan = plan
            if [m.recipe.id for m in plan.meals] == before:
                # Be honest rather than pretending we changed something.
                self.messenger.send(
                    "That's the best I can do with the recipes I have — "
                    "share more recipe links and I'll have more to choose from.",
                    to=Role.OWNER)
                return "plan_unchanged"
            return "plan_revised"
        if self.state.awaiting == Awaiting.ORDER_APPROVAL:
            self.messenger.send(
                "For the grocery order, reply 'approve' or 'reject'.", to=Role.OWNER)
            return "noop"
        self.messenger.send("Nothing is pending to revise.", to=Role.OWNER)
        return "noop"

    # -- cook sends the material list -------------------------------------- #
    def on_grocery_list(self, text: str) -> str:
        items = self.llm.parse_grocery_list(text)
        if not items:
            self.messenger.send(
                "I couldn't read any items in that list — please resend.", to=Role.COOK)
            return "empty_list"
        order = self.order_agent.build_order(items)  # asks owner to approve
        self.state.order = order
        self.state.awaiting = Awaiting.ORDER_APPROVAL
        return "order_requested"

    def on_cook_feedback(self, text: str) -> str:
        return "noted"  # general cook chatter, no action

    # -- someone asks for the plan ----------------------------------------- #
    def on_query(self, date: str) -> str:
        """Show today's plan, generating one on demand if there isn't one yet."""
        plan = self.state.plan
        if plan is None or plan.status == PlanStatus.REJECTED or plan.date != date:
            return "plan_generated" if self.start_daily(date) else "no_recipes"
        from ..agents.diet import format_plan
        self.messenger.send(format_plan(plan), to=Role.OWNER)
        return "answered"

    # -- recipe add (independent of pending state) ------------------------- #
    def on_add_recipe(self, url: str):
        return self.adder.handle(url)
