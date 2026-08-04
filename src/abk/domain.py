"""Pure domain models, enums, errors and small helpers. No I/O, no external deps."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class Role(str, Enum):
    OWNER = "owner"
    COOK = "cook"
    UNKNOWN = "unknown"


class Intent(str, Enum):
    """Coarse intent. The router resolves APPROVE/REJECT/REVISE to plan-vs-order
    using the current conversation state, so the classifier stays context-free."""
    APPROVE = "approve"
    REJECT = "reject"
    REVISE = "revise"
    ADD_RECIPE = "add_recipe"
    GROCERY_LIST = "grocery_list"
    COOK_FEEDBACK = "cook_feedback"
    QUERY = "query"
    OTHER = "other"


class MealSlot(str, Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


ORDERED_SLOTS = [MealSlot.BREAKFAST, MealSlot.LUNCH, MealSlot.DINNER, MealSlot.SNACK]


class PlanStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class OrderStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PLACED = "placed"
    EMPTY = "empty"  # nothing to order


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class AbkError(Exception):
    """Base error."""


class TranscriptUnavailable(AbkError):
    """The link has no usable transcript/captions."""


class RecipeExtractionError(AbkError):
    """The transcript could not be turned into a structured recipe."""


class NoRecipesError(AbkError):
    """The recipe book is empty, so no plan can be built."""


class ProviderNotConfigured(AbkError):
    """A grocery provider was selected but is not configured."""


# --------------------------------------------------------------------------- #
# Value objects
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Macros:
    calories: float = 0.0
    protein: float = 0.0
    carbs: float = 0.0
    fat: float = 0.0

    def __add__(self, other: "Macros") -> "Macros":
        return Macros(
            self.calories + other.calories,
            self.protein + other.protein,
            self.carbs + other.carbs,
            self.fat + other.fat,
        )


def _norm(name: str) -> str:
    return name.strip().lower()


@dataclass(frozen=True)
class Ingredient:
    name: str
    quantity: float = 1.0
    unit: str = "unit"

    @property
    def key(self) -> tuple[str, str]:
        return (_norm(self.name), _norm(self.unit))


# --------------------------------------------------------------------------- #
# Entities
# --------------------------------------------------------------------------- #
def _new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Recipe:
    name: str
    macros: Macros = field(default_factory=Macros)
    ingredients: list[Ingredient] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    source_link: Optional[str] = None
    id: str = field(default_factory=_new_id)


@dataclass
class Meal:
    slot: MealSlot
    recipe: Recipe


@dataclass
class MealPlan:
    date: str
    meals: list[Meal] = field(default_factory=list)
    revision: int = 0
    status: PlanStatus = PlanStatus.PROPOSED
    id: str = field(default_factory=_new_id)

    @property
    def totals(self) -> Macros:
        total = Macros()
        for meal in self.meals:
            total = total + meal.recipe.macros
        return total

    def required_ingredients(self) -> list[Ingredient]:
        """Aggregate ingredients across all meals by (name, unit)."""
        return aggregate_ingredients(
            ing for meal in self.meals for ing in meal.recipe.ingredients
        )


@dataclass
class Profile:
    name: str = "owner"
    goal: str = "balanced"
    macro_targets: Macros = field(default_factory=lambda: Macros(2000, 120, 220, 60))
    meals_per_day: int = 3
    preferences: list[str] = field(default_factory=list)
    restrictions: list[str] = field(default_factory=list)
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    body_type: str = ""


@dataclass(frozen=True)
class GroceryItem:
    name: str
    quantity: float = 1.0
    unit: str = "unit"


@dataclass
class GroceryOrder:
    items: list[GroceryItem] = field(default_factory=list)
    status: OrderStatus = OrderStatus.PENDING
    provider: Optional[str] = None
    id: str = field(default_factory=_new_id)

    @property
    def is_empty(self) -> bool:
        return len(self.items) == 0


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def aggregate_ingredients(ingredients) -> list[Ingredient]:
    """Sum quantities of ingredients that share a (name, unit) key.
    Preserves first-seen order for stable output."""
    order: list[tuple[str, str]] = []
    acc: dict[tuple[str, str], Ingredient] = {}
    for ing in ingredients:
        k = ing.key
        if k in acc:
            existing = acc[k]
            acc[k] = Ingredient(existing.name, existing.quantity + ing.quantity, existing.unit)
        else:
            acc[k] = ing
            order.append(k)
    return [acc[k] for k in order]
