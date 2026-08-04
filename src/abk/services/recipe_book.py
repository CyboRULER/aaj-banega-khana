"""Recipe book: repository interface + in-memory adapter + optional markdown mirror."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional

from ..domain import Recipe


class RecipeRepository(ABC):
    @abstractmethod
    def add(self, recipe: Recipe) -> None: ...

    @abstractmethod
    def all(self) -> list[Recipe]: ...

    @abstractmethod
    def get(self, recipe_id: str) -> Optional[Recipe]: ...

    @abstractmethod
    def find_by_name(self, name: str) -> Optional[Recipe]: ...


class InMemoryRecipeRepository(RecipeRepository):
    def __init__(self) -> None:
        self._by_id: dict[str, Recipe] = {}

    def add(self, recipe: Recipe) -> None:
        self._by_id[recipe.id] = recipe

    def all(self) -> list[Recipe]:
        return list(self._by_id.values())

    def get(self, recipe_id: str) -> Optional[Recipe]:
        return self._by_id.get(recipe_id)

    def find_by_name(self, name: str) -> Optional[Recipe]:
        target = name.strip().lower()
        for r in self._by_id.values():
            if r.name.strip().lower() == target:
                return r
        return None


class MarkdownMirror:
    """Writes each recipe as a markdown file into a directory ('its directory')."""

    def __init__(self, directory: str) -> None:
        self.directory = directory

    def write(self, recipe: Recipe) -> str:
        os.makedirs(self.directory, exist_ok=True)
        safe = "".join(c if c.isalnum() else "-" for c in recipe.name.lower()).strip("-")
        path = os.path.join(self.directory, f"{safe or 'recipe'}-{recipe.id}.md")
        lines = [
            f"# {recipe.name}", "",
            f"- source: {recipe.source_link or 'n/a'}",
            f"- macros: {recipe.macros.calories} kcal | "
            f"P{recipe.macros.protein} C{recipe.macros.carbs} F{recipe.macros.fat}",
            "", "## Ingredients", "",
        ]
        lines += [f"- {i.quantity:g} {i.unit} {i.name}" for i in recipe.ingredients]
        lines += ["", "## Steps", ""]
        lines += [f"{n}. {s}" for n, s in enumerate(recipe.steps, 1)]
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return path


class RecipeBook:
    """Service facade. Deduplicates by name; optionally mirrors to markdown."""

    def __init__(self, repo: RecipeRepository, mirror: Optional[MarkdownMirror] = None) -> None:
        self.repo = repo
        self.mirror = mirror

    def add_recipe(self, recipe: Recipe) -> tuple[Recipe, bool]:
        """Returns (recipe, created). If a recipe with the same name exists, it is
        kept and `created` is False (idempotent add)."""
        existing = self.repo.find_by_name(recipe.name)
        if existing is not None:
            return existing, False
        self.repo.add(recipe)
        if self.mirror is not None:
            self.mirror.write(recipe)
        return recipe, True

    def all(self) -> list[Recipe]:
        return self.repo.all()

    def get(self, recipe_id: str) -> Optional[Recipe]:
        return self.repo.get(recipe_id)
