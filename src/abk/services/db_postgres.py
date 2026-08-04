"""Postgres-backed persistence (psycopg 3).

Mirrors the SQLite repositories in db.py for hosted deploys where the local
filesystem is not durable. Selected by setting ABK_DATABASE_URL; without it the
app keeps using SQLite, so tests and offline runs need no extra dependency.

Serialisation is shared with db.py - only the SQL dialect differs.
"""
from __future__ import annotations

import json
from typing import Optional

from ..domain import Ingredient, Macros, Profile, Recipe
from .db import (_ingredients_from_json, _ingredients_to_json, _macros_from_json,
                 _macros_to_json)
from .profile import ProfileStore
from .recipe_book import RecipeRepository

# `seq` gives recipes a stable insertion order; Postgres has no rowid.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    seq          BIGSERIAL,
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


def connect(database_url: str):
    """Open (and initialise) the Postgres database.

    Raises RuntimeError with an actionable message if psycopg is missing, since
    it is an optional extra only needed for hosted deploys.
    """
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - depends on install extras
        raise RuntimeError(
            "ABK_DATABASE_URL is set but psycopg is not installed. "
            "Install it with: pip install 'psycopg[binary]>=3.1'") from exc

    conn = psycopg.connect(database_url, autocommit=True, row_factory=dict_row)
    with conn.cursor() as cur:
        cur.execute(_SCHEMA)
    return conn


def _row_to_recipe(row) -> Recipe:
    return Recipe(
        name=row["name"],
        macros=_macros_from_json(row["macros"]),
        ingredients=_ingredients_from_json(row["ingredients"]),
        steps=json.loads(row["steps"]),
        source_link=row["source_link"],
        id=row["id"],
    )


class PostgresRecipeRepository(RecipeRepository):
    def __init__(self, conn) -> None:
        self.conn = conn

    def add(self, recipe: Recipe) -> None:
        name_key = recipe.name.strip().lower()
        with self.conn.cursor() as cur:
            # SQLite's INSERT OR REPLACE replaces on *any* unique conflict, so
            # clear a same-name row under a different id before upserting on id.
            cur.execute("DELETE FROM recipes WHERE name_key = %s AND id <> %s",
                        (name_key, recipe.id))
            cur.execute(
                "INSERT INTO recipes "
                "(id, name, name_key, macros, ingredients, steps, source_link) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (id) DO UPDATE SET "
                "name = EXCLUDED.name, name_key = EXCLUDED.name_key, "
                "macros = EXCLUDED.macros, ingredients = EXCLUDED.ingredients, "
                "steps = EXCLUDED.steps, source_link = EXCLUDED.source_link",
                (recipe.id, recipe.name, name_key,
                 _macros_to_json(recipe.macros), _ingredients_to_json(recipe.ingredients),
                 json.dumps(recipe.steps), recipe.source_link))

    def all(self) -> list[Recipe]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM recipes ORDER BY seq")
            return [_row_to_recipe(r) for r in cur.fetchall()]

    def get(self, recipe_id: str) -> Optional[Recipe]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM recipes WHERE id = %s", (recipe_id,))
            row = cur.fetchone()
        return _row_to_recipe(row) if row else None

    def find_by_name(self, name: str) -> Optional[Recipe]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM recipes WHERE name_key = %s",
                        (name.strip().lower(),))
            row = cur.fetchone()
        return _row_to_recipe(row) if row else None


class PostgresProfileStore(ProfileStore):
    def __init__(self, conn, default: Optional[Profile] = None) -> None:
        self.conn = conn
        if default is not None and self._read() is None:
            self.set(default)

    def _read(self) -> Optional[Profile]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT data FROM profile WHERE id = 1")
            row = cur.fetchone()
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
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO profile (id, data) VALUES (1, %s) "
                "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data", (data,))
