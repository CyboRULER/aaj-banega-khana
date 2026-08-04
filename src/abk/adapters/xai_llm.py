"""Live LLM adapter for xAI (Grok), via the OpenAI-compatible chat API.

Uses only the stdlib (urllib) so it needs no extra dependency. Any failure
degrades gracefully to the offline FakeLLM heuristics instead of crashing.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Callable, Optional

from ..config import Settings
from ..domain import Ingredient, Intent, Macros, Meal, Profile, Recipe, Role
from ..llm import FakeLLM, LLMClient

_INTENT_SYSTEM = (
    "You classify WhatsApp messages in a meal-planning group with an owner and a cook.\n"
    "Reply with EXACTLY ONE of these words and nothing else:\n"
    "approve - agrees to the pending meal plan or grocery order\n"
    "reject - cancels the pending plan or order\n"
    "revise - wants the meal plan changed (e.g. 'lighter', 'no rice', 'yes but...')\n"
    "add_recipe - shares a recipe link to save\n"
    "grocery_list - lists ingredients/materials to buy (e.g. '200g paneer, 1kg onion')\n"
    "cook_feedback - the cook reports kitchen status unrelated to a shopping list\n"
    "query - asks about the menu, macros or timing\n"
    "other - anything else"
)
_EXTRACT_SYSTEM = (
    "Extract a cooking recipe from the transcript. Reply ONLY with JSON: "
    '{"name": str, "macros": {"calories": num, "protein": num, "carbs": num, "fat": num}, '
    '"ingredients": [{"name": str, "quantity": num, "unit": str}], "steps": [str]}'
)


class XaiLLM(LLMClient):
    def __init__(self, settings: Settings,
                 transport: Optional[Callable[[dict], dict]] = None) -> None:
        self.settings = settings
        self._transport = transport or self._http
        self._fallback = FakeLLM()

    # -- transport --------------------------------------------------------- #
    def _http(self, payload: dict) -> dict:  # pragma: no cover - network path
        url = self.settings.xai_base_url.rstrip("/") + "/chat/completions"
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.xai_api_key}",
            }, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _chat(self, system: str, prompt: str, max_tokens: int = 1024) -> str:
        payload = {
            "model": self.settings.xai_model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        return self._parse_content(self._transport(payload))

    @staticmethod
    def _parse_content(data: dict) -> str:
        return data["choices"][0]["message"]["content"].strip()

    # -- LLMClient --------------------------------------------------------- #
    def classify(self, text: str, role: Role) -> Intent:
        try:
            word = self._chat(_INTENT_SYSTEM,
                              f"sender={role.value}\nmessage: {text}", max_tokens=16).lower()
            word = word.strip().strip(".'\"")
            for intent in Intent:  # exact match wins
                if word == intent.value:
                    return intent
            for intent in Intent:  # then substring
                if intent.value in word:
                    return intent
        except Exception:
            pass
        return self._fallback.classify(text, role)

    def extract_recipe(self, transcript: str, url: str) -> Recipe:
        try:
            raw = self._chat(_EXTRACT_SYSTEM, transcript[:8000], max_tokens=1500)
            data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
            m = data.get("macros", {})
            return Recipe(
                name=data.get("name", "Untitled recipe"),
                macros=Macros(m.get("calories", 0), m.get("protein", 0),
                              m.get("carbs", 0), m.get("fat", 0)),
                ingredients=[Ingredient(i["name"], float(i.get("quantity", 1)),
                                        i.get("unit", "unit"))
                             for i in data.get("ingredients", [])],
                steps=list(data.get("steps", [])), source_link=url)
        except Exception:
            return self._fallback.extract_recipe(transcript, url)

    def plan_meals(self, profile: Profile, recipes: list[Recipe],
                   feedback: Optional[str] = None) -> list[Meal]:
        """Ask the model to pick recipes per slot, honouring the profile and any
        feedback ('replace chicken', 'lighter'...). Falls back to the rule engine."""
        from ..domain import NoRecipesError, MealSlot, ORDERED_SLOTS
        if not recipes:
            raise NoRecipesError("recipe book is empty")
        try:
            menu = "\n".join(
                f"- {r.name} ({r.macros.calories:g} kcal, P{r.macros.protein:g}); "
                f"ingredients: {', '.join(i.name for i in r.ingredients) or 'n/a'}"
                for r in recipes)
            n = max(1, profile.meals_per_day)
            slots = [s.value for s in ORDERED_SLOTS[:n]]
            t = profile.macro_targets
            system = (
                "You plan a day of meals by choosing from a fixed recipe list.\n"
                "Reply ONLY with JSON: {\"meals\": [{\"slot\": str, \"recipe\": str}]}\n"
                "Use recipe names EXACTLY as given. One entry per requested slot.\n"
                "Respect the user's feedback strictly - if they ask to remove or "
                "replace an ingredient, do not pick any recipe containing it.")
            prompt = (
                f"Goal: {profile.goal}. Daily targets: {t.calories:g} kcal, "
                f"{t.protein:g}g protein.\nSlots: {', '.join(slots)}\n"
                f"Recipes:\n{menu}\n"
                + (f"\nUser feedback to honour: {feedback}" if feedback else ""))
            raw = self._chat(system, prompt, max_tokens=600)
            data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
            by_name = {r.name.strip().lower(): r for r in recipes}
            meals: list[Meal] = []
            for i, entry in enumerate(data.get("meals", [])[:n]):
                recipe = by_name.get(str(entry.get("recipe", "")).strip().lower())
                if recipe is None:
                    continue
                try:
                    slot = MealSlot(str(entry.get("slot", "")).strip().lower())
                except ValueError:
                    slot = ORDERED_SLOTS[i] if i < len(ORDERED_SLOTS) else MealSlot.SNACK
                meals.append(Meal(slot=slot, recipe=recipe))
            if meals:
                return meals
        except Exception:
            pass
        return self._fallback.plan_meals(profile, recipes, feedback)

    def parse_grocery_list(self, text: str):
        return self._fallback.parse_grocery_list(text)
