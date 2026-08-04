import unittest

from abk.domain import (
    Ingredient, Macros, Meal, MealPlan, MealSlot, Recipe, aggregate_ingredients,
)


class TestDomain(unittest.TestCase):
    def test_macros_add(self):
        total = Macros(100, 10, 20, 5) + Macros(50, 5, 10, 2)
        self.assertEqual(total, Macros(150, 15, 30, 7))

    def test_aggregate_by_name_and_unit(self):
        agg = aggregate_ingredients([
            Ingredient("onion", 1, "unit"),
            Ingredient("Onion", 2, "unit"),   # same key (case-insensitive)
            Ingredient("onion", 3, "g"),        # different unit -> separate
        ])
        self.assertEqual(len(agg), 2)
        self.assertEqual(agg[0].quantity, 3)  # 1 + 2 units
        self.assertEqual(agg[1].quantity, 3)  # grams stay separate

    def test_plan_totals_and_required(self):
        r1 = Recipe("A", Macros(300, 10, 40, 5), [Ingredient("rice", 1, "cup")])
        r2 = Recipe("B", Macros(200, 20, 10, 8),
                    [Ingredient("rice", 1, "cup"), Ingredient("dal", 1, "cup")])
        plan = MealPlan("2026-07-27",
                        [Meal(MealSlot.LUNCH, r1), Meal(MealSlot.DINNER, r2)])
        self.assertEqual(plan.totals, Macros(500, 30, 50, 13))
        req = {i.name: i.quantity for i in plan.required_ingredients()}
        self.assertEqual(req["rice"], 2)  # aggregated across meals
        self.assertEqual(req["dal"], 1)


if __name__ == "__main__":
    unittest.main()
