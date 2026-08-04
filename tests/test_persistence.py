import os
import tempfile
import unittest

from abk.app import build_app
from abk.config import Settings
from abk.domain import Ingredient, Macros, Profile, Recipe
from abk.services.db import SqliteProfileStore, SqliteRecipeRepository, connect


class TestSqliteRepos(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")

    def test_recipe_roundtrip(self):
        repo = SqliteRecipeRepository(self.conn)
        r = Recipe("Palak Paneer", Macros(400, 22, 18, 26),
                   [Ingredient("paneer", 200, "g")], ["blanch", "simmer"],
                   "https://youtu.be/x")
        repo.add(r)
        got = repo.get(r.id)
        self.assertEqual(got.name, "Palak Paneer")
        self.assertEqual(got.macros.protein, 22)
        self.assertEqual(got.ingredients[0].unit, "g")
        self.assertEqual(got.steps, ["blanch", "simmer"])
        self.assertEqual(got.source_link, "https://youtu.be/x")

    def test_find_by_name_case_insensitive(self):
        repo = SqliteRecipeRepository(self.conn)
        repo.add(Recipe("Poha", Macros(300)))
        self.assertIsNotNone(repo.find_by_name("poha"))
        self.assertIsNone(repo.find_by_name("nope"))

    def test_profile_roundtrip(self):
        store = SqliteProfileStore(self.conn)
        store.set(Profile(name="Sample User", goal="muscle gain",
                          macro_targets=Macros(2800, 165, 360, 78),
                          meals_per_day=4, weight_kg=72, height_cm=178,
                          body_type="lean-fat"))
        got = store.get()
        self.assertEqual(got.goal, "muscle gain")
        self.assertEqual(got.macro_targets.protein, 165)
        self.assertEqual(got.meals_per_day, 4)
        self.assertEqual(got.weight_kg, 72)


class TestPersistenceSurvivesRestart(unittest.TestCase):
    def test_data_survives_new_app_instance(self):
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "abk.sqlite3")
            settings = Settings(db_path=db)

            app1 = build_app(settings, persist=True)
            app1.add_recipe(Recipe("Poha", Macros(300),
                                   [Ingredient("poha", 2, "cup")], ["cook"]))
            app1.seed_profile(Profile(name="Sample User", goal="muscle gain"))

            # brand new app pointed at the same file
            app2 = build_app(settings, persist=True)
            names = [r.name for r in app2.recipe_book.all()]
            self.assertIn("Poha", names)
            self.assertEqual(app2.profile_store.get().goal, "muscle gain")


if __name__ == "__main__":
    unittest.main()
