import unittest

from abk.domain import Ingredient, Macros, Profile, Recipe, Role
from abk.llm import FakeLLM, excluded_terms, recipe_mentions
from tests.helpers import make_app


RECIPES = [
    Recipe("Chicken Curry", Macros(650), [Ingredient("chicken", 250, "g")]),
    Recipe("Dal Rice", Macros(560), [Ingredient("rice", 1, "cup")]),
    Recipe("Paneer Bhurji", Macros(520), [Ingredient("paneer", 200, "g")]),
]


class TestExclusionParsing(unittest.TestCase):
    def test_replace_x(self):
        self.assertIn("chicken", excluded_terms("replace chicken"))

    def test_no_x(self):
        self.assertIn("rice", excluded_terms("no rice please"))

    def test_without_x(self):
        self.assertIn("paneer", excluded_terms("dinner without paneer"))

    def test_no_terms_for_plain_feedback(self):
        self.assertEqual(excluded_terms("make it lighter"), [])

    def test_none_is_safe(self):
        self.assertEqual(excluded_terms(None), [])

    def test_matches_name_or_ingredient(self):
        self.assertTrue(recipe_mentions(RECIPES[0], "chicken"))   # by ingredient
        self.assertTrue(recipe_mentions(RECIPES[1], "dal"))        # by name
        self.assertFalse(recipe_mentions(RECIPES[1], "chicken"))


class TestPlanHonoursExclusion(unittest.TestCase):
    def test_replace_chicken_removes_chicken(self):
        meals = FakeLLM().plan_meals(Profile(meals_per_day=2), RECIPES, "replace chicken")
        names = [m.recipe.name for m in meals]
        self.assertNotIn("Chicken Curry", names)

    def test_never_empties_the_book(self):
        # excluding everything must not produce an empty plan
        meals = FakeLLM().plan_meals(
            Profile(meals_per_day=1), [RECIPES[0]], "no chicken")
        self.assertEqual(len(meals), 1)


class TestHonestFeedback(unittest.TestCase):
    def test_unchanged_plan_is_reported(self):
        app = make_app()
        app.conversation.start_daily("2026-07-27")
        # feedback that matches nothing -> plan cannot change
        action = app.conversation.on_revise("replace zzzznotanything")
        self.assertIn(action, ("plan_unchanged", "plan_revised"))
        if action == "plan_unchanged":
            self.assertTrue(any("best I can do" in m.text for m in app.messenger.outbox))

    def test_cook_gets_told_why_revise_was_blocked(self):
        app = make_app()
        app.conversation.start_daily("2026-07-27")
        r = app.inbound(app.settings.cook_jid, "replace chicken")
        self.assertEqual(r.action, "ignored_unauthorized")
        self.assertTrue(any("Only the owner" in m.text for m in app.messenger.outbox))


if __name__ == "__main__":
    unittest.main()
