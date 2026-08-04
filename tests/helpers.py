from abk.app import build_app
from abk.domain import Ingredient, Macros, Profile, Recipe


def make_app(meals_per_day=3):
    app = build_app(profile=Profile(meals_per_day=meals_per_day))
    app.add_recipe(Recipe("Poha", Macros(300, 8, 50, 6),
                          [Ingredient("poha", 2, "cup")], ["cook"], "https://youtu.be/POHA"))
    app.add_recipe(Recipe("Dal Rice", Macros(550, 20, 90, 8),
                          [Ingredient("rice", 1, "cup"), Ingredient("dal", 1, "cup")],
                          ["cook"], "https://youtu.be/DAL"))
    app.add_recipe(Recipe("Palak Paneer", Macros(400, 22, 18, 26),
                          [Ingredient("spinach", 2, "cup"), Ingredient("paneer", 200, "g")],
                          ["cook"], "https://youtu.be/PANEER"))
    return app
