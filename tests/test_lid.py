import unittest

from abk.app import build_app
from abk.config import Settings
from abk.domain import Intent, Role


def app_with_lids():
    return build_app(Settings(
        owner_jid="911111111111@s.whatsapp.net", cook_jid="922222222222@s.whatsapp.net",
        owner_lid="111111111111111@lid", cook_lid="222222222222222@lid"))


class TestLidRoleResolution(unittest.TestCase):
    """WhatsApp addresses group members by LID, not phone JID (real bug: the
    cook's message arrived as 222222222222222@lid and was ignored)."""

    def setUp(self):
        self.app = app_with_lids()
        self.r = self.app.router

    def test_phone_jid_still_resolves(self):
        self.assertEqual(self.r.resolve_role("911111111111@s.whatsapp.net"), Role.OWNER)
        self.assertEqual(self.r.resolve_role("922222222222@s.whatsapp.net"), Role.COOK)

    def test_lid_in_jid_field_resolves(self):
        # gateway couldn't map it, so the LID arrives as the jid
        self.assertEqual(self.r.resolve_role("222222222222222@lid"), Role.COOK)

    def test_lid_in_lid_field_resolves(self):
        self.assertEqual(
            self.r.resolve_role("unknown@s.whatsapp.net", "222222222222222@lid"), Role.COOK)

    def test_unknown_lid_ignored(self):
        self.assertEqual(self.r.resolve_role("999@lid", "999@lid"), Role.UNKNOWN)

    def test_cook_grocery_list_via_lid_end_to_end(self):
        res = self.app.inbound("222222222222222@lid", "need 2 kg onion, 1 packet bread")
        self.assertEqual(res.role, Role.COOK)
        self.assertEqual(res.intent, Intent.GROCERY_LIST)
        self.assertEqual(res.action, "order_requested")

    def test_empty_lid_config_does_not_match_blank_sender(self):
        app = build_app(Settings(owner_jid="a@s.whatsapp.net", cook_jid="b@s.whatsapp.net"))
        self.assertEqual(app.router.resolve_role("", ""), Role.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
