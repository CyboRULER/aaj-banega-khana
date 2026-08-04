"""SQLite-backed persistence (stdlib sqlite3 only).

Provides durable implementations of RecipeRepository and ProfileStore so recipes
and the profile survive restarts. Recipes store their ingredients/steps/macros as
JSON blobs - simple and sufficient for a single-user app.
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Optional

from ..domain import Ingredient, Macros, Profile, Recipe
from .profile import ProfileStore
from .recipe_book import RecipeRepository

_SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    name_key     TEXT NOT NULL UNIQUE,
    macros       TEXT NOT NULL,
    ingredients  TEXT NOT NULL,
    steps        TEXT NOT NULL,
    source_link  TEXT
);
CREATE TABLE IF NOT EXISTS profile (
    id    INTEGER PRIMARY KEY CHECK (id = 1),
    data  TEXT NOT NULL
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    """Open (and initialise) the database. Use ':memory:' for tests."""
    if db_path != ":memory:":
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


# --------------------------------------------------------------------------- #
# serialisation helpers
# --------------------------------------------------------------------------- #
def _macros_to_json(m: Macros) -> str:
    return json.dumps({"calories": m.calories, "protein": m.protein,
                       "carbs": m.carbs, "fat": m.fat})


def _macros_from_json(raw: str) -> Macros:
    d = json.loads(raw)
    return Macros(d.get("calories", 0), d.get("protein", 0),
                  d.get("carbs", 0), d.get("fat", 0))


def _ingredients_to_json(items: list[Ingredient]) -> str:
    return json.dumps([{"name": i.name, "quantity": i.quantity, "unit": i.unit}
                       for i in items])


def _ingredients_from_json(raw: str) -> list[Ingredient]:
    return [Ingredient(d["name"], float(d.get("quantity", 1)), d.get("unit", "unit"))
            for d in json.loads(raw)]


def _row_to_recipe(row: sqlite3.Row) -> Recipe:
    return Recipe(
        name=row["name"],
        macros=_macros_from_json(row["macros"]),
        ingredients=_ingredients_from_json(row["ingredients"]),
        steps=json.loads(row["steps"]),
        source_link=row["source_link"],
        id=row["id"],
    )


# --------------------------------------------------------------------------- #
# repositories
# --------------------------------------------------------------------------- #
class SqliteRecipeRepository(RecipeRepository):
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(self, recipe: Recipe) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO recipes "
            "(id, name, name_key, macros, ingredients, steps, source_link) "
            "VALUES (?,?,?,?,?,?,?)",
            (recipe.id, recipe.name, recipe.name.strip().lower(),
             _macros_to_json(recipe.macros), _ingredients_to_json(recipe.ingredients),
             json.dumps(recipe.steps), recipe.source_link))
        self.conn.commit()

    def all(self) -> list[Recipe]:
        rows = self.conn.execute("SELECT * FROM recipes ORDER BY rowid").fetchall()
        return [_row_to_recipe(r) for r in rows]

    def get(self, recipe_id: str) -> Optional[Recipe]:
        row = self.conn.execute(
            "SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        return _row_to_recipe(row) if row else None

    def find_by_name(self, name: str) -> Optional[Recipe]:
        row = self.conn.execute(
            "SELECT * FROM recipes WHERE name_key = ?",
            (name.strip().lower(),)).fetchone()
        return _row_to_recipe(row) if row else None


class SqliteProfileStore(ProfileStore):
    def __init__(self, conn: sqlite3.Connection, default: Optional[Profile] = None) -> None:
        self.conn = conn
        if default is not None and self._read() is None:
            self.set(default)

    def _read(self) -> Optional[Profile]:
        row = self.conn.execute("SELECT data FROM profile WHERE id = 1").fetchone()
        if row is None:
            return None
        d = json.loads(row["data"])
        return Profile(
            name=d.get("name", "owner"), goal=d.get("goal", "balanced"),
            macro_targets=_macros_from_json(json.dumps(d.get("macro_targets", {}))),
            meals_per_day=int(d.get("meals_per_day", 3)),
            preferences=list(d.get("preferences", [])),
            restrictions=list(d.get("restrictions", [])),
            weight_kg=d.get("weight_kg"), height_cm=d.get("height_cm"),
            body_type=d.get("body_type", ""))

    def get(self) -> Profile:
        return self._read() or Profile()

    def set(self, profile: Profile) -> None:
        data = json.dumps({
            "name": profile.name, "goal": profile.goal,
            "macro_targets": json.loads(_macros_to_json(profile.macro_targets)),
            "meals_per_day": profile.meals_per_day,
            "preferences": profile.preferences, "restrictions": profile.restrictions,
            "weight_kg": profile.weight_kg, "height_cm": profile.height_cm,
            "body_type": profile.body_type,
        })
        self.conn.execute(
            "INSERT INTO profile (id, data) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data", (data,))
        self.conn.commit()
