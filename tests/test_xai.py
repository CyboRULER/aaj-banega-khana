import unittest

from abk.adapters.xai_llm import XaiLLM
from abk.config import Settings
from abk.domain import Intent, Role


def _canned(content):
    return lambda payload: {"choices": [{"message": {"content": content}}]}


class TestXaiAdapter(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(xai_api_key="test", llm_provider="xai")

    def test_parse_content(self):
        data = {"choices": [{"message": {"content": " approve "}}]}
        self.assertEqual(XaiLLM._parse_content(data), "approve")

    def test_classify_uses_api_response(self):
        llm = XaiLLM(self.settings, transport=_canned("revise"))
        self.assertEqual(llm.classify("change lunch", Role.OWNER), Intent.REVISE)

    def test_classify_falls_back_on_transport_error(self):
        def boom(payload):
            raise RuntimeError("network down")
        llm = XaiLLM(self.settings, transport=boom)
        # falls back to offline heuristics -> url still detected as add_recipe
        self.assertEqual(
            llm.classify("see https://youtu.be/x", Role.OWNER), Intent.ADD_RECIPE)

    def test_extract_recipe_from_json(self):
        content = ('{"name": "Poha", "macros": {"calories": 300, "protein": 8, '
                   '"carbs": 50, "fat": 6}, "ingredients": [{"name": "poha", '
                   '"quantity": 2, "unit": "cup"}], "steps": ["rinse", "toss"]}')
        llm = XaiLLM(self.settings, transport=_canned(content))
        recipe = llm.extract_recipe("some transcript", "u")
        self.assertEqual(recipe.name, "Poha")
        self.assertEqual(recipe.macros.protein, 8)
        self.assertEqual(recipe.ingredients[0].unit, "cup")

    def test_provider_selection(self):
        self.assertEqual(Settings(xai_api_key="k").resolve_provider(), "xai")
        self.assertEqual(Settings(anthropic_api_key="k").resolve_provider(), "anthropic")
        self.assertEqual(Settings().resolve_provider(), "offline")
        self.assertEqual(
            Settings(xai_api_key="k", llm_provider="offline").resolve_provider(), "offline")


class TestIntentPromptCoverage(unittest.TestCase):
    """Regression: every Intent must be listed in the classifier prompt, else the
    model can never return it (grocery_list was missing once)."""

    def test_all_intents_present_in_prompt(self):
        from abk.adapters.xai_llm import _INTENT_SYSTEM
        from abk.domain import Intent
        missing = [i.value for i in Intent if i.value not in _INTENT_SYSTEM]
        self.assertEqual(missing, [], f"intents missing from prompt: {missing}")

    def test_exact_match_preferred(self):
        llm = XaiLLM(Settings(xai_api_key="k"), transport=_canned("grocery_list"))
        self.assertEqual(llm.classify("200g paneer", Role.COOK), Intent.GROCERY_LIST)

    def test_strips_punctuation_and_case(self):
        llm = XaiLLM(Settings(xai_api_key="k"), transport=_canned(" Approve. "))
        self.assertEqual(llm.classify("ok", Role.OWNER), Intent.APPROVE)


if __name__ == "__main__":
    unittest.main()
