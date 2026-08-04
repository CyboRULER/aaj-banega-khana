"""Cook notifier: post cooking instructions (menu + recipe links) to the cook,
and ask the cook for the material list to buy."""
from __future__ import annotations

from ..domain import MealPlan, Role
from ..services.messaging import Messenger


def notify_cook(plan: MealPlan, messenger: Messenger) -> None:
    lines = ["Cook — today's menu:"]
    for meal in plan.meals:
        r = meal.recipe
        link = f" | recipe: {r.source_link}" if r.source_link else ""
        lines.append(f"- {meal.slot.value}: {r.name}{link}")
    lines.append("")
    lines.append("Please send the list of materials you need and I'll get them ordered.")
    messenger.send("\n".join(lines), to=Role.COOK)
