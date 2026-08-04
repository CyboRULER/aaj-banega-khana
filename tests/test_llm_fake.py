import unittest

from abk.domain import (
    Intent, NoRecipesError, Profile, RecipeExtractionError, Recipe, Macros, Role,
)
from abk.llm import FakeLLM


class TestFakeLLMClassify(unittest.TestCase):
    def setUp(self):
        self.llm = FakeLLM()

    def test_url_is_add_recipe(self):
        self.assertEqual(
            self.llm.classify("found this https://youtu.be/x", Role.OWNER),
            Intent.ADD_RECIPE)

    def test_plain_approve(self):
        self.assertEqual(self.llm.classify("approve", Role.OWNER), Intent.APPROVE)

    def test_reject(self):
        self.assertEqual(self.llm.classify("cancel that", Role.OWNER), Intent.REJECT)

    def test_revise(self):
        self.assertEqual(self.llm.classify("make it lighter", Role.OWNER), Intent.REVISE)

    def test_owner_need_phrase_is_revise_not_list(self):
        # "need lighter option" must not be mistaken for a grocery list
        self.assertEqual(
            self.llm.classify("need lighter option", Role.OWNER), Intent.REVISE)

    def test_ambiguous_approve_with_condition_is_revise(self):
        self.assertEqual(
            self.llm.classify("yes but without rice", Role.OWNER), Intent.REVISE)

    def test_cook_material_list_is_grocery_list(self):
        self.assertEqual(
            self.llm.classify("need 200g paneer, 1 kg onion, bread", Role.COOK),
            Intent.GROCERY_LIST)

    def test_cook_prose_is_feedback(self):
        self.assertEqual(
            self.llm.classify("thoda late ho jayega today", Role.COOK),
            Intent.COOK_FEEDBACK)

    def test_query(self):
        self.assertEqual(self.llm.classify("what's the menu?", Role.OWNER), Intent.QUERY)


class TestGroceryListParsing(unittest.TestCase):
    def setUp(self):
        self.llm = FakeLLM()

    def test_parse_comma_list_with_quantities(self):
        items = self.llm.parse_grocery_list("need 200g paneer, 1 kg onion, 2 packet bread, salt")
        by = {i.name: (i.quantity, i.unit) for i in items}
        self.assertEqual(by["paneer"], (200, "g"))
        self.assertEqual(by["onion"], (1, "kg"))
        self.assertEqual(by["bread"], (2, "packet"))
        self.assertEqual(by["salt"], (1, "unit"))

    def test_parse_newline_and_and_separators(self):
        items = self.llm.parse_grocery_list("paneer and bread\n2 cup rice")
        names = sorted(i.name for i in items)
        self.assertEqual(names, ["bread", "paneer", "rice"])

    def test_parse_empty(self):
        self.assertEqual(self.llm.parse_grocery_list(""), [])


class TestFakeLLMExtract(unittest.TestCase):
    def setUp(self):
        self.llm = FakeLLM()

    def test_extract_structured(self):
        transcript = ("NAME: Poha\nMACROS: 300, 8, 50, 6\n"
                      "INGREDIENTS:\n2 cup poha\n1 unit onion\nSTEPS:\nRinse\nToss\n")
        recipe = self.llm.extract_recipe(transcript, "u")
        self.assertEqual(recipe.name, "Poha")
        self.assertEqual(recipe.macros.calories, 300)
        self.assertEqual(len(recipe.ingredients), 2)
        self.assertEqual(recipe.ingredients[0].quantity, 2)
        self.assertEqual(recipe.source_link, "u")

    def test_empty_transcript_raises(self):
        with self.assertRaises(RecipeExtractionError):
            self.llm.extract_recipe("   ", "u")

    def test_transcript_without_recipe_raises(self):
        with self.assertRaises(RecipeExtractionError):
            self.llm.extract_recipe("just some chatter with no sections", "u")


class TestFakeLLMPlan(unittest.TestCase):
    def setUp(self):
        self.llm = FakeLLM()
        self.recipes = [
            Recipe("Light", Macros(200)), Recipe("Heavy", Macros(700)),
            Recipe("Mid", Macros(400)),
        ]

    def test_no_recipes_raises(self):
        with self.assertRaises(NoRecipesError):
            self.llm.plan_meals(Profile(), [])

    def test_default_prefers_higher_calorie_first(self):
        meals = self.llm.plan_meals(Profile(meals_per_day=1), self.recipes)
        self.assertEqual(meals[0].recipe.name, "Heavy")

    def test_lighter_feedback_prefers_low_calorie(self):
        meals = self.llm.plan_meals(Profile(meals_per_day=1), self.recipes,
                                    feedback="make it lighter")
        self.assertEqual(meals[0].recipe.name, "Light")


if __name__ == "__main__":
    unittest.main()
