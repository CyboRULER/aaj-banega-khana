import unittest

from abk.domain import OrderStatus, PlanStatus, Role
from abk.orchestration.conversation import Awaiting
from tests.helpers import make_app


class TestHappyPath(unittest.TestCase):
    def test_full_day(self):
        app = make_app()
        owner, cook = app.settings.owner_jid, app.settings.cook_jid

        plan = app.conversation.start_daily("2026-07-27")
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.meals), 3)
        self.assertEqual(app.conversation.state.awaiting, Awaiting.PLAN_APPROVAL)

        # owner approves the plan -> cook is notified, and we wait for the list
        r = app.inbound(owner, "approve")
        self.assertEqual(r.action, "plan_approved")
        self.assertEqual(app.conversation.state.plan.status, PlanStatus.APPROVED)
        self.assertTrue(any(m.to == Role.COOK for m in app.messenger.outbox))
        self.assertEqual(app.conversation.state.awaiting, Awaiting.IDLE)

        # cook sends the material list -> owner asked to approve the order
        r = app.inbound(cook, "need 200g paneer, 1 kg onion, 2 packet bread")
        self.assertEqual(r.action, "order_requested")
        self.assertEqual(app.conversation.state.awaiting, Awaiting.ORDER_APPROVAL)
        names = [i.name for i in app.conversation.state.order.items]
        self.assertIn("paneer", names)
        self.assertIn("bread", names)

        # owner approves the order -> placed
        r = app.inbound(owner, "approve")
        self.assertEqual(r.action, "order_placed")
        self.assertEqual(app.conversation.state.order.status, OrderStatus.PLACED)
        self.assertEqual(app.conversation.state.awaiting, Awaiting.IDLE)


class TestReviseLoop(unittest.TestCase):
    def test_revise_increments_revision(self):
        app = make_app()
        owner = app.settings.owner_jid
        app.conversation.start_daily("2026-07-27")
        self.assertEqual(app.conversation.state.plan.revision, 0)
        r = app.inbound(owner, "make it lighter")
        self.assertEqual(r.action, "plan_revised")
        self.assertEqual(app.conversation.state.plan.revision, 1)
        self.assertEqual(app.conversation.state.awaiting, Awaiting.PLAN_APPROVAL)


class TestReject(unittest.TestCase):
    def test_reject_plan(self):
        app = make_app()
        owner = app.settings.owner_jid
        app.conversation.start_daily("2026-07-27")
        r = app.inbound(owner, "cancel")
        self.assertEqual(r.action, "plan_rejected")
        self.assertEqual(app.conversation.state.plan.status, PlanStatus.REJECTED)
        self.assertEqual(app.conversation.state.awaiting, Awaiting.IDLE)

    def test_reject_order(self):
        app = make_app()
        owner, cook = app.settings.owner_jid, app.settings.cook_jid
        app.conversation.start_daily("2026-07-27")
        app.inbound(owner, "approve")
        app.inbound(cook, "need 1 kg onion, bread")
        r = app.inbound(owner, "cancel")
        self.assertEqual(r.action, "order_rejected")
        self.assertEqual(app.conversation.state.order.status, OrderStatus.REJECTED)


class TestEmptyList(unittest.TestCase):
    def test_unreadable_list_is_reprompted(self):
        app = make_app()
        # calling the handler directly with no items
        action = app.conversation.on_grocery_list("   ")
        self.assertEqual(action, "empty_list")
        self.assertTrue(any(m.to == Role.COOK for m in app.messenger.outbox))


class TestConcurrentRecipeAdd(unittest.TestCase):
    def test_link_during_plan_approval_does_not_disturb_plan(self):
        app = make_app()
        owner = app.settings.owner_jid
        app.conversation.start_daily("2026-07-27")
        plan_id = app.conversation.state.plan.id
        recipes_before = len(app.recipe_book.all())

        r = app.inbound(owner, "adding https://youtu.be/PANEER")  # already exists -> skip
        self.assertEqual(r.action, "recipe_added")
        self.assertEqual(app.conversation.state.awaiting, Awaiting.PLAN_APPROVAL)
        self.assertEqual(app.conversation.state.plan.id, plan_id)
        self.assertEqual(len(app.recipe_book.all()), recipes_before)


if __name__ == "__main__":
    unittest.main()
