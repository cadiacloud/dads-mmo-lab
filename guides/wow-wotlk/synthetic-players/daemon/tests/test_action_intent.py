import unittest

from synthetic_daemon.action_intent import detect_explicit_action


class ExplicitActionIntentTests(unittest.TestCase):
    def test_routes_mage_refreshment_requests(self) -> None:
        self.assertEqual(
            detect_explicit_action("Lyra, please make max-level food and water", 8),
            "REFRESHMENT",
        )
        self.assertEqual(
            detect_explicit_action("Do you have a mage table for the party?", 8),
            "REFRESHMENT",
        )

    def test_routes_mage_buff_requests(self) -> None:
        self.assertEqual(
            detect_explicit_action("Please buff the party", 8),
            "BUFF ARCANE BRILLIANCE",
        )
        self.assertEqual(
            detect_explicit_action("Could you cast Arcane Brilliance?", 8),
            "BUFF ARCANE BRILLIANCE",
        )

    def test_routes_allowlisted_portal_requests(self) -> None:
        self.assertEqual(
            detect_explicit_action("Can you open a portal to Thunderbluff?", 8),
            "PORTAL THUNDER BLUFF",
        )

    def test_does_not_route_non_requests_or_non_mages(self) -> None:
        self.assertIsNone(detect_explicit_action("I already have plenty of water", 8))
        self.assertIsNone(detect_explicit_action("Please make food and water", 1))
        self.assertIsNone(detect_explicit_action("Open a portal to Goldshire", 8))


if __name__ == "__main__":
    unittest.main()
