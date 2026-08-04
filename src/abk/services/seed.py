"""Load profile and seed recipes from JSON config files into a running App."""
from __future__ import annotations

import json
import os
from typing import Optional

from ..domain import Ingredient, Macros, Profile, Recipe


def load_profile(path: str) -> Optional[Profile]:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    mt = data.get("macro_targets", {})
    return Profile(
        name=data.get("name", "owner"),
        goal=data.get("goal", "balanced"),
        macro_targets=Macros(mt.get("calories", 0), mt.get("protein", 0),
                             mt.get("carbs", 0), mt.get("fat", 0)),
        meals_per_day=int(data.get("meals_per_day", 3)),
        preferences=list(data.get("preferences", [])),
        restrictions=list(data.get("restrictions", [])),
        weight_kg=data.get("weight_kg"),
        height_cm=data.get("height_cm"),
        body_type=data.get("body_type", ""),
    )


def load_recipes(path: str) -> list[Recipe]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    recipes: list[Recipe] = []
    for r in data:
        m = r.get("macros", {})
        recipes.append(Recipe(
            name=r["name"],
            macros=Macros(m.get("calories", 0), m.get("protein", 0),
                          m.get("carbs", 0), m.get("fat", 0)),
            ingredients=[Ingredient(i["name"], float(i.get("quantity", 1)),
                                    i.get("unit", "unit")) for i in r.get("ingredients", [])],
            steps=list(r.get("steps", [])),
            source_link=r.get("source_link"),
        ))
    return recipes


def apply_seeds(app, profile_path: str, recipes_path: str) -> None:
    profile = load_profile(profile_path)
    if profile is not None:
        app.seed_profile(profile)
    for recipe in load_recipes(recipes_path):
        app.add_recipe(recipe)
