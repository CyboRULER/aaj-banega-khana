import unittest

from abk.domain import Intent, PlanStatus, Role
from abk.orchestration.conversation import Awaiting
from tests.helpers import make_app


class TestPlanOnDemand(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.owner = self.app.settings.owner_jid
        self.cook = self.app.settings.cook_jid

    def test_asking_generates_a_plan_when_none_exists(self):
        r = self.app.inbound(self.owner, "what's the menu today?")
        self.assertEqual(r.intent, Intent.QUERY)
        self.assertEqual(r.action, "plan_generated")
        self.assertIsNotNone(self.app.conversation.state.plan)
        self.assertEqual(self.app.conversation.state.awaiting, Awaiting.PLAN_APPROVAL)

    def test_asking_again_shows_the_same_plan(self):
        self.app.inbound(self.owner, "what's the menu?")
        plan_id = self.app.conversation.state.plan.id
        r = self.app.inbound(self.owner, "what's the menu?")
        self.assertEqual(r.action, "answered")
        self.assertEqual(self.app.conversation.state.plan.id, plan_id)

    def test_asking_after_reject_generates_a_fresh_plan(self):
        self.app.inbound(self.owner, "what's the menu?")
        first = self.app.conversation.state.plan.id
        self.app.inbound(self.owner, "cancel")
        self.assertEqual(self.app.conversation.state.plan.status, PlanStatus.REJECTED)
        r = self.app.inbound(self.owner, "what's the menu?")
        self.assertEqual(r.action, "plan_generated")
        self.assertNotEqual(self.app.conversation.state.plan.id, first)

    def test_cook_can_ask_too(self):
        r = self.app.inbound(self.cook, "what's cooking today?")
        self.assertEqual(r.role, Role.COOK)
        self.assertIn(r.action, ("plan_generated", "answered"))

    def test_empty_recipe_book_says_so(self):
        from abk.app import build_app
        app = build_app()  # no recipes
        r = app.inbound(app.settings.owner_jid, "what's the menu?")
        self.assertEqual(r.action, "no_recipes")
        self.assertTrue(any("empty" in m.text for m in app.messenger.outbox))


if __name__ == "__main__":
    unittest.main()
