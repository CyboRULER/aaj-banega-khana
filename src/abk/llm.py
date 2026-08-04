"""LLM boundary.

`LLMClient` is the interface the agents depend on. `FakeLLM` is a deterministic,
rule-based implementation so the whole product runs and is fully testable OFFLINE
(no API key). Live adapters (xai_llm, claude_llm) are lazy-imported.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Optional

from .domain import (
    GroceryItem,
    Ingredient,
    Intent,
    Macros,
    Meal,
    MealSlot,
    NoRecipesError,
    ORDERED_SLOTS,
    Profile,
    Recipe,
    RecipeExtractionError,
    Role,
)

URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

_APPROVE_WORDS = {"approve", "approved", "yes", "yep", "sure", "go ahead",
                  "sounds good", "confirm", "confirmed", "👍", "perfect"}
_REJECT_WORDS = {"reject", "cancel", "nope", "don't", "dont", "stop"}
_REVISE_WORDS = {"change", "instead", "swap", "replace", "lighter", "light", "heavier",
                 "more", "less", "different", "revise", "another", "but", "except", "without"}
_QUERY_WORDS = {"what", "when", "how", "menu", "macros", "calories", "eta", "?"}

# Strong signals that a message is a shopping/material list (not prose).
_LIST_WORDS = {"grocery", "groceries", "list", "material", "materials",
               "ingredients", "chahiye", "laana", "mangwa", "mangwana", "saman", "samaan"}
_QTY_RE = re.compile(r"\d+\s*[a-zA-Z]")


def find_url(text: str) -> Optional[str]:
    m = URL_RE.search(text or "")
    return m.group(0) if m else None


def _looks_like_list(text: str) -> bool:
    t = (text or "").lower()
    if "," in t or "\n" in t:      # multiple items
        return True
    if _QTY_RE.search(t):          # a quantity like "200g" or "2 packet"
        return True
    return any(w in t for w in _LIST_WORDS)


def parse_grocery_list(text: str) -> list[GroceryItem]:
    """Split a free-text material list into GroceryItems.

    Handles commas, newlines and 'and'/'aur' separators, strips list-intro words,
    and parses 'qty unit name' when present."""
    if not text:
        return []
    chunks = re.split(r"[,\n]| and | aur ", text)
    items: list[GroceryItem] = []
    for chunk in chunks:
        c = chunk.strip().lower()
        # strip leading intro words like "need", "i need", "buy", "please"
        for w in ("please", "i", "need", "buy", "order", "get", "want",
                  "required", "grocery", "groceries", "list", "material"):
            if c.startswith(w + " "):
                c = c[len(w) + 1:].strip()
        c = c.strip(" .:-")
        if not c or c in _LIST_WORDS:
            continue
        ing = _parse_ingredient(c)
        items.append(GroceryItem(ing.name, ing.quantity, ing.unit))
    return items


class LLMClient(ABC):
    @abstractmethod
    def classify(self, text: str, role: Role) -> Intent: ...

    @abstractmethod
    def extract_recipe(self, transcript: str, url: str) -> Recipe: ...

    @abstractmethod
    def plan_meals(self, profile: Profile, recipes: list[Recipe],
                   feedback: Optional[str] = None) -> list[Meal]: ...

    @abstractmethod
    def parse_grocery_list(self, text: str) -> list[GroceryItem]: ...


class FakeLLM(LLMClient):
    """Deterministic rules. Doubles as the offline engine and the test double."""

    def classify(self, text: str, role: Role) -> Intent:
        t = (text or "").lower().strip()
        if not t:
            return Intent.OTHER
        if find_url(text):
            return Intent.ADD_RECIPE

        has_approve = any(w in t for w in _APPROVE_WORDS)
        has_revise = any(w in t for w in _REVISE_WORDS)
        has_reject = any(w in t for w in _REJECT_WORDS)

        # Ambiguous "yes but no rice" / "yes, lighter" -> treat as a revision.
        if has_approve and has_revise:
            return Intent.REVISE

        # A material/shopping list (usually from the cook) -> ordering path.
        if _looks_like_list(t) and parse_grocery_list(text):
            return Intent.GROCERY_LIST

        if has_revise:
            return Intent.REVISE
        if has_approve:
            return Intent.APPROVE
        if has_reject:
            return Intent.REJECT
        if any(w in t for w in _QUERY_WORDS):
            return Intent.QUERY
        # A cook message that isn't a list or a command is general feedback.
        if role == Role.COOK:
            return Intent.COOK_FEEDBACK
        return Intent.OTHER

    def parse_grocery_list(self, text: str) -> list[GroceryItem]:
        return parse_grocery_list(text)

    def extract_recipe(self, transcript: str, url: str) -> Recipe:
        """Parse a lightly-structured transcript.

        Convention understood by the offline engine: sections `NAME:`,
        `MACROS: cal,protein,carbs,fat`, `INGREDIENTS:` (lines `qty unit name`),
        `STEPS:` (one per line). Live adapters do full NL extraction instead.
        """
        if not transcript or not transcript.strip():
            raise RecipeExtractionError("empty transcript")
        name = "Untitled recipe"
        macros = Macros()
        ingredients: list[Ingredient] = []
        steps: list[str] = []
        section = None
        for raw in transcript.splitlines():
            line = raw.strip()
            if not line:
                continue
            low = line.lower()
            if low.startswith("name:"):
                name = line.split(":", 1)[1].strip() or name
                section = None
            elif low.startswith("macros:"):
                nums = [float(x) for x in re.findall(r"[\d.]+", line.split(":", 1)[1])]
                nums += [0.0] * (4 - len(nums))
                macros = Macros(nums[0], nums[1], nums[2], nums[3])
                section = None
            elif low.startswith("ingredients:"):
                section = "ing"
            elif low.startswith("steps:"):
                section = "steps"
            elif section == "ing":
                ingredients.append(_parse_ingredient(line))
            elif section == "steps":
                steps.append(line.lstrip("-* "))
        if not ingredients and not steps:
            raise RecipeExtractionError("no ingredients or steps found in transcript")
        return Recipe(name=name, macros=macros, ingredients=ingredients,
                      steps=steps, source_link=url)

    def plan_meals(self, profile: Profile, recipes: list[Recipe],
                   feedback: Optional[str] = None) -> list[Meal]:
        if not recipes:
            raise NoRecipesError("recipe book is empty")
        # Honour "replace chicken" / "no rice" / "without paneer" style feedback.
        for term in excluded_terms(feedback):
            filtered = [r for r in recipes if not recipe_mentions(r, term)]
            if filtered:  # never filter the book down to nothing
                recipes = filtered
        want_lighter = bool(feedback) and any(
            w in feedback.lower() for w in ("light", "less", "fewer", "low"))
        ordered = sorted(recipes, key=lambda r: r.macros.calories, reverse=not want_lighter)
        n = max(1, profile.meals_per_day)
        meals: list[Meal] = []
        for i in range(n):
            slot = ORDERED_SLOTS[i] if i < len(ORDERED_SLOTS) else MealSlot.SNACK
            recipe = ordered[i % len(ordered)]
            meals.append(Meal(slot=slot, recipe=recipe))
        return meals


_EXCLUDE_RE = re.compile(
    r"\b(?:replace|without|remove|avoid|skip|no|not?\s+want|hatao|nahi)\s+"
    r"([a-z][a-z ]{2,})", re.IGNORECASE)
_STOP = {"the", "a", "an", "it", "this", "that", "and", "with", "from", "please",
         "any", "some", "more", "less", "food", "meal", "meals", "plan", "today"}


def excluded_terms(feedback: Optional[str]) -> list[str]:
    """Pull ingredient/dish words the user wants left out of the plan."""
    if not feedback:
        return []
    terms: list[str] = []
    for match in _EXCLUDE_RE.finditer(feedback.lower()):
        for word in match.group(1).split()[:2]:  # 'chicken curry' -> both words
            word = word.strip(" .,!")
            if len(word) > 2 and word not in _STOP and word not in terms:
                terms.append(word)
    return terms


def recipe_mentions(recipe: Recipe, term: str) -> bool:
    term = term.lower()
    if term in recipe.name.lower():
        return True
    return any(term in ing.name.lower() for ing in recipe.ingredients)


def _parse_ingredient(line: str) -> Ingredient:
    """Parse `2 cup rice` / `paneer` / `200 g paneer`."""
    line = line.lstrip("-* ").strip()
    m = re.match(r"^([\d.]+)\s*([a-zA-Z]+)?\s+(.*)$", line)
    if m and m.group(3):
        qty = float(m.group(1))
        unit = (m.group(2) or "unit").strip()
        name = m.group(3).strip()
        return Ingredient(name=name, quantity=qty, unit=unit)
    return Ingredient(name=line, quantity=1.0, unit="unit")


def build_llm(settings) -> LLMClient:
    """Factory: pick the LLM backend (xai | anthropic | offline) from settings."""
    provider = settings.resolve_provider() if hasattr(settings, "resolve_provider") else "offline"
    if provider == "xai":
        try:
            from .adapters.xai_llm import XaiLLM
            return XaiLLM(settings)
        except Exception:  # pragma: no cover - falls back if anything is off
            pass
    elif provider == "anthropic":
        try:
            from .adapters.claude_llm import ClaudeLLM
            return ClaudeLLM(settings)
        except Exception:  # pragma: no cover - falls back if SDK missing
            pass
    return FakeLLM()
