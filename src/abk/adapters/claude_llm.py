"""Live LLM adapter backed by the Anthropic Claude API.

Only imported when ANTHROPIC_API_KEY is set. Falls back to FakeLLM heuristics if a
call fails, so the system degrades gracefully rather than crashing.
"""
from __future__ import annotations

import json
from typing import Optional

from ..config import Settings
from ..domain import Ingredient, Intent, Macros, Meal, Profile, Recipe, Role
from ..llm import FakeLLM, LLMClient


_INTENT_SYSTEM = (
    "You classify WhatsApp messages in a meal-planning group with an owner and a cook.\n"
    "Reply with EXACTLY ONE of these words and nothing else:\n"
    "approve, reject, revise, add_recipe, grocery_list, cook_feedback, query, other.\n"
    "Use grocery_list when the message lists ingredients/materials to buy."
)


class ClaudeLLM(LLMClient):
    def __init__(self, settings: Settings) -> None:
        import anthropic  # noqa: F401 - ensure SDK is present
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.settings = settings
        self._fallback = FakeLLM()

    def _message(self, model: str, system: str, prompt: str, max_tokens: int = 1024) -> str:
        resp = self._client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": prompt}])
        return "".join(block.text for block in resp.content if block.type == "text").strip()

    def classify(self, text: str, role: Role) -> Intent:
        try:
            word = self._message(self.settings.extractor_model, _INTENT_SYSTEM,
                                 f"role={role.value}\nmessage: {text}", max_tokens=8).lower()
            for intent in Intent:
                if intent.value in word:
                    return intent
        except Exception:
            pass
        return self._fallback.classify(text, role)

    def extract_recipe(self, transcript: str, url: str) -> Recipe:
        system = ("Extract a cooking recipe from the transcript. Reply as JSON with keys "
                  "name, macros{calories,protein,carbs,fat}, "
                  "ingredients[{name,quantity,unit}], steps[].")
        try:
            raw = self._message(self.settings.extractor_model, system, transcript[:8000])
            data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
            m = data.get("macros", {})
            return Recipe(
                name=data.get("name", "Untitled recipe"),
                macros=Macros(m.get("calories", 0), m.get("protein", 0),
                              m.get("carbs", 0), m.get("fat", 0)),
                ingredients=[Ingredient(i["name"], float(i.get("quantity", 1)),
                                        i.get("unit", "unit")) for i in data.get("ingredients", [])],
                steps=list(data.get("steps", [])), source_link=url)
        except Exception:
            return self._fallback.extract_recipe(transcript, url)

    def plan_meals(self, profile: Profile, recipes: list[Recipe],
                   feedback: Optional[str] = None) -> list[Meal]:
        # Recipe selection stays deterministic/testable; Claude could rank here.
        return self._fallback.plan_meals(profile, recipes, feedback)

    def parse_grocery_list(self, text: str):
        return self._fallback.parse_grocery_list(text)
