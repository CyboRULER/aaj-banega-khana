"""List (or inspect) the recipe book.

Run:  python3 apps/recipes.py            # list all recipes
      python3 apps/recipes.py paneer     # show full detail for matches
      python3 apps/recipes.py --add URL  # add a recipe from a link right now
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from abk.config import Settings, load_env_file  # noqa: E402
from abk.services.db import SqliteRecipeRepository, connect  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def show(r, full: bool) -> None:
    m = r.macros
    print(f"\n{r.name}  —  {m.calories:g} kcal | P{m.protein:g} C{m.carbs:g} F{m.fat:g}")
    if r.source_link:
        print(f"  source: {r.source_link}")
    if full:
        print("  ingredients:")
        for i in r.ingredients:
            print(f"    - {i.quantity:g} {i.unit} {i.name}")
        print("  steps:")
        for n, s in enumerate(r.steps, 1):
            print(f"    {n}. {s}")


def main() -> None:
    load_env_file(os.path.join(ROOT, ".env"))
    settings = Settings.from_env()
    args = sys.argv[1:]

    if args and args[0] == "--add":
        if len(args) < 2:
            print("usage: python3 apps/recipes.py --add <url>")
            return
        from abk.app import build_app
        from abk.adapters.youtube import YouTubeTranscriber
        from abk.services.messaging import FakeMessenger
        msgr = FakeMessenger()
        app = build_app(settings, messenger=msgr, transcriber=YouTubeTranscriber(),
                        persist=True)
        recipe = app.adder.handle(args[1])
        print(msgr.texts()[-1] if msgr.texts() else "no response")
        if recipe:
            show(recipe, full=True)
        return

    conn = connect(os.path.join(ROOT, settings.db_path))
    recipes = SqliteRecipeRepository(conn).all()
    needle = args[0].lower() if args else None
    matches = [r for r in recipes if not needle or needle in r.name.lower()]

    print(f"\nRecipe book: {len(recipes)} recipe(s)" +
          (f", {len(matches)} matching '{needle}'" if needle else ""))
    print("-" * 46)
    for r in matches:
        show(r, full=bool(needle))
    print()


if __name__ == "__main__":
    main()
