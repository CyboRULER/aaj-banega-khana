"""Diet Agent: profile + recipe book -> full-day meal plan (with revise loop)."""
from __future__ import annotations

from typing import Optional

from ..domain import MealPlan, Profile, Role
from ..llm import LLMClient
from ..services.messaging import Messenger
from ..services.profile import ProfileStore
from ..services.recipe_book import RecipeBook


def format_plan(plan: MealPlan) -> str:
    lines = [f"Meal plan for {plan.date} (revision {plan.revision}):"]
    for meal in plan.meals:
        r = meal.recipe
        lines.append(f"- {meal.slot.value}: {r.name} ({r.macros.calories:g} kcal)")
    t = plan.totals
    lines.append(f"Total: {t.calories:g} kcal | P{t.protein:g} C{t.carbs:g} F{t.fat:g}")
    lines.append("Reply 'approve' to confirm, or tell me what to change.")
    return "\n".join(lines)


class DietAgent:
    def __init__(self, profile_store: ProfileStore, recipe_book: RecipeBook,
                 llm: LLMClient, messenger: Messenger) -> None:
        self.profile_store = profile_store
        self.recipe_book = recipe_book
        self.llm = llm
        self.messenger = messenger

    def propose(self, date: str, feedback: Optional[str] = None,
                revision: int = 0) -> MealPlan:
        profile: Profile = self.profile_store.get()
        recipes = self.recipe_book.all()
        meals = self.llm.plan_meals(profile, recipes, feedback)  # may raise NoRecipesError
        plan = MealPlan(date=date, meals=meals, revision=revision)
        self.messenger.send(format_plan(plan), to=Role.OWNER)
        return plan
