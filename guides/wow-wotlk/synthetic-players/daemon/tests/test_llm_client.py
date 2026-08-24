import unittest

from synthetic_daemon.llm_client import SyntheticLLMClient


class ExtractActionTests(unittest.TestCase):
    def test_extracts_bounded_posture_action(self) -> None:
        text, action = SyntheticLLMClient._extract_action("Rest a moment. [ACTION: sit]")

        self.assertEqual(text, "Rest a moment.")
        self.assertEqual(action, "SIT")

    def test_normalizes_bounded_emote_action(self) -> None:
        text, action = SyntheticLLMClient._extract_action("For the Horde! [ACTION: emote 004]")

        self.assertEqual(text, "For the Horde!")
        self.assertEqual(action, "EMOTE 4")

    def test_rejects_command_action_and_hides_tag(self) -> None:
        text, action = SyntheticLLMClient._extract_action("Following. [ACTION: COMMAND .bot follow]")

        self.assertEqual(text, "Following.")
        self.assertIsNone(action)

    def test_rejects_out_of_range_or_ambiguous_actions(self) -> None:
        _, out_of_range = SyntheticLLMClient._extract_action("No. [ACTION: EMOTE 501]")
        _, multiple = SyntheticLLMClient._extract_action("No. [ACTION: SIT] [ACTION: STAND]")

        self.assertIsNone(out_of_range)
        self.assertIsNone(multiple)

    def test_extracts_allowlisted_portal_destination(self) -> None:
        text, action = SyntheticLLMClient._extract_action(
            "I'll open the way. [ACTION: portal thunderbluff]"
        )

        self.assertEqual(text, "I'll open the way.")
        self.assertEqual(action, "PORTAL THUNDER BLUFF")

    def test_extracts_mage_provision_and_buff_actions(self) -> None:
        _, refreshment = SyntheticLLMClient._extract_action(
            "I'll set a table. [ACTION: REFRESHMENT]"
        )
        _, buff = SyntheticLLMClient._extract_action(
            "Gather close. [ACTION: BUFF ARCANE BRILLIANCE]"
        )

        self.assertEqual(refreshment, "REFRESHMENT")
        self.assertEqual(buff, "BUFF ARCANE BRILLIANCE")

    def test_rejects_unknown_or_command_like_portal_destination(self) -> None:
        _, unknown = SyntheticLLMClient._extract_action("No. [ACTION: PORTAL GOLDshire]")
        _, injected = SyntheticLLMClient._extract_action("No. [ACTION: PORTAL ORGRIMMAR; .server shutdown]")

        self.assertIsNone(unknown)
        self.assertIsNone(injected)


if __name__ == "__main__":
    unittest.main()
