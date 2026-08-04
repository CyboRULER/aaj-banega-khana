import os
import tempfile
import unittest

from abk.domain import (
    GroceryItem, GroceryOrder, Ingredient, Macros, OrderStatus,
    ProviderNotConfigured, Recipe,
)
from abk.adapters.instamart import InstamartOrderer
from abk.services.grocery import ManualListAdapter
from abk.services.recipe_book import (
    InMemoryRecipeRepository, MarkdownMirror, RecipeBook,
)


class TestGroceryProviders(unittest.TestCase):
    def test_manual_empty_order(self):
        res = ManualListAdapter().place(GroceryOrder(items=[]))
        self.assertEqual(res.status, OrderStatus.EMPTY)

    def test_manual_nonempty_order(self):
        order = GroceryOrder(items=[GroceryItem("dal", 1, "cup")])
        res = ManualListAdapter().place(order)
        self.assertEqual(res.status, OrderStatus.PLACED)
        self.assertIn("dal", res.message)

    def test_instamart_not_configured_raises(self):
        order = GroceryOrder(items=[GroceryItem("dal", 1, "cup")])
        with self.assertRaises(ProviderNotConfigured):
            InstamartOrderer().place(order)

    def test_instamart_empty_order_is_safe(self):
        res = InstamartOrderer().place(GroceryOrder(items=[]))
        self.assertEqual(res.status, OrderStatus.EMPTY)


class TestRecipeBook(unittest.TestCase):
    def test_dedupe_by_name(self):
        book = RecipeBook(InMemoryRecipeRepository())
        r1, created1 = book.add_recipe(Recipe("Poha", Macros(300)))
        r2, created2 = book.add_recipe(Recipe("poha", Macros(999)))  # same name
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(len(book.all()), 1)
        self.assertEqual(r2.id, r1.id)

    def test_markdown_mirror_writes_file(self):
        with tempfile.TemporaryDirectory() as d:
            book = RecipeBook(InMemoryRecipeRepository(), MarkdownMirror(d))
            book.add_recipe(Recipe("Palak Paneer", Macros(400),
                                   [Ingredient("paneer", 200, "g")], ["cook"]))
            files = os.listdir(d)
            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].endswith(".md"))


if __name__ == "__main__":
    unittest.main()
