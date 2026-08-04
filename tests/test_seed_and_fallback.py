import os
import unittest

from abk.agents.order import OrderAgent
from abk.domain import GroceryItem, GroceryOrder, OrderStatus
from abk.adapters.instamart import InstamartOrderer
from abk.services.messaging import FakeMessenger
from abk.services.seed import load_profile, load_recipes

CONFIG = os.path.join(os.path.dirname(__file__), "..", "config")


class TestInstamartFallback(unittest.TestCase):
    def test_place_falls_back_to_manual_when_mcp_not_configured(self):
        agent = OrderAgent(InstamartOrderer(), FakeMessenger())
        order = GroceryOrder(items=[GroceryItem("dal", 1, "cup")])
        result = agent.place(order)
        self.assertEqual(result.status, OrderStatus.PLACED)
        self.assertEqual(result.provider, "manual")
        self.assertIn("dal", result.message)


class TestSeedLoaders(unittest.TestCase):
    def test_load_profile(self):
        profile = load_profile(os.path.join(CONFIG, "profile.json"))
        self.assertIsNotNone(profile)
        self.assertEqual(profile.goal, "muscle gain")
        self.assertEqual(profile.meals_per_day, 4)
        self.assertEqual(profile.macro_targets.protein, 160)
        self.assertEqual(profile.weight_kg, 70)

    def test_load_recipes(self):
        recipes = load_recipes(os.path.join(CONFIG, "recipes.json"))
        self.assertGreaterEqual(len(recipes), 5)
        names = [r.name for r in recipes]
        self.assertIn("Paneer Bhurji with Roti", names)
        paneer = next(r for r in recipes if r.name == "Paneer Bhurji with Roti")
        self.assertEqual(paneer.macros.protein, 30)
        self.assertTrue(paneer.ingredients)

    def test_missing_file_is_safe(self):
        self.assertIsNone(load_profile("nope.json"))
        self.assertEqual(load_recipes("nope.json"), [])


if __name__ == "__main__":
    unittest.main()
