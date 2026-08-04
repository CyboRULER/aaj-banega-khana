import unittest

from abk.domain import Intent, Role
from abk.orchestration.conversation import Awaiting
from tests.helpers import make_app


class TestRouterRolesAndAuthority(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.owner = self.app.settings.owner_jid
        self.cook = self.app.settings.cook_jid

    def test_unknown_sender_ignored(self):
        r = self.app.inbound("stranger@s.whatsapp.net", "approve")
        self.assertEqual(r.role, Role.UNKNOWN)
        self.assertEqual(r.action, "ignored_unknown_sender")

    def test_cook_cannot_approve(self):
        self.app.conversation.start_daily("2026-07-27")
        r = self.app.inbound(self.cook, "approve")
        self.assertEqual(r.intent, Intent.APPROVE)
        self.assertEqual(r.action, "ignored_unauthorized")

    def test_cook_may_add_recipe(self):
        # harmless action: no spending, no authorisation
        r = self.app.inbound(self.cook, "https://youtu.be/PANEER")
        self.assertEqual(r.intent, Intent.ADD_RECIPE)
        self.assertEqual(r.action, "recipe_added")

    def test_cook_still_cannot_revise(self):
        self.app.conversation.start_daily("2026-07-27")
        r = self.app.inbound(self.cook, "make it lighter")
        self.assertEqual(r.action, "ignored_unauthorized")

    def test_cook_can_send_material_list(self):
        r = self.app.inbound(self.cook, "need 200g paneer, 1 kg onion")
        self.assertEqual(r.intent, Intent.GROCERY_LIST)
        self.assertEqual(r.action, "order_requested")
        self.assertEqual(self.app.conversation.state.awaiting, Awaiting.ORDER_APPROVAL)

    def test_owner_approve_with_nothing_pending_is_noop(self):
        r = self.app.inbound(self.owner, "approve")
        self.assertEqual(r.action, "noop")

    def test_query_generates_plan_on_demand(self):
        r = self.app.inbound(self.owner, "what's the menu?")
        self.assertEqual(r.intent, Intent.QUERY)
        # no plan yet today -> asking creates one
        self.assertEqual(r.action, "plan_generated")


if __name__ == "__main__":
    unittest.main()
