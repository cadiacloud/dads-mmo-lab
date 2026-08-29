import unittest

from synthetic_daemon.director import (
    IntentStatus,
    IntentType,
    detect_explicit_intent,
    fallback_result_message,
    format_state_for_prompt,
    has_direction_request_cue,
    message_supports_intent,
)


class ExplicitDirectorIntentTests(unittest.TestCase):
    def test_routes_movement_intents(self) -> None:
        self.assertEqual(detect_explicit_intent("Brog, follow me"), IntentType.FOLLOW)
        self.assertEqual(
            detect_explicit_intent("Please hold this position"),
            IntentType.HOLD_POSITION,
        )
        self.assertEqual(detect_explicit_intent("Fall back!"), IntentType.RETREAT)

    def test_routes_group_duty_decisions_before_generic_follow(self) -> None:
        self.assertEqual(
            detect_explicit_intent("Lyra, report to us now"),
            IntentType.REPORT_TO_GROUP,
        )
        self.assertEqual(
            detect_explicit_intent("Celene, keep working on your routine"),
            IntentType.CONTINUE_ROUTINE,
        )

    def test_routes_targeted_combat_intents(self) -> None:
        self.assertEqual(
            detect_explicit_intent("Attack my target"),
            IntentType.ATTACK_PLAYER_TARGET,
        )
        self.assertEqual(
            detect_explicit_intent("Please pull this mob back"),
            IntentType.PULL_PLAYER_TARGET,
        )

    def test_routes_party_preparation(self) -> None:
        self.assertEqual(
            detect_explicit_intent("Everyone buff up and get ready"),
            IntentType.PREPARE_PARTY,
        )

    def test_routes_lyra_and_celene_capabilities(self) -> None:
        self.assertEqual(
            detect_explicit_intent("Lyra, sheep my target"),
            IntentType.POLYMORPH_PLAYER_TARGET,
        )
        self.assertEqual(
            detect_explicit_intent("Celene, sap this target"),
            IntentType.SAP_PLAYER_TARGET,
        )
        self.assertEqual(
            detect_explicit_intent("Celene, stun that enemy"),
            IntentType.STUN_PLAYER_TARGET,
        )
        self.assertEqual(
            detect_explicit_intent("Lyra, please cast slow fall"),
            IntentType.SLOW_FALL_ISSUER,
        )
        self.assertEqual(
            detect_explicit_intent("Celene, power up and use your cooldowns"),
            IntentType.POWER_UP,
        )

    def test_routes_farming_lifecycle(self) -> None:
        self.assertEqual(
            detect_explicit_intent("Celene, go farm and gather"),
            IntentType.START_FARMING,
        )
        self.assertEqual(
            detect_explicit_intent("Celene, stop farming"),
            IntentType.STOP_FARMING,
        )

    def test_routes_economy_lifecycle_and_work(self) -> None:
        self.assertEqual(
            detect_explicit_intent("Lyra, start economy work"),
            IntentType.START_ECONOMY,
        )
        self.assertEqual(
            detect_explicit_intent("Celene, work the auction house"),
            IntentType.WORK_AUCTION_HOUSE,
        )
        self.assertEqual(
            detect_explicit_intent("Lyra, craft something useful"),
            IntentType.CRAFT_SUPPLIES,
        )
        self.assertEqual(
            detect_explicit_intent("Celene, collect your mail"),
            IntentType.COLLECT_MAIL,
        )
        self.assertEqual(
            detect_explicit_intent("Celene, deposit your ore into the guild bank"),
            IntentType.DEPOSIT_GUILD_BANK,
        )
        self.assertEqual(
            detect_explicit_intent("Put it in the guildbank"),
            IntentType.DEPOSIT_GUILD_BANK,
        )
        self.assertEqual(
            detect_explicit_intent("Lyra, share some gold with me"),
            IntentType.SHARE_GOLD,
        )
        self.assertEqual(
            detect_explicit_intent("Celene, stop economy work"),
            IntentType.STOP_ECONOMY,
        )

    def test_ignores_statements_without_a_clear_order(self) -> None:
        self.assertIsNone(detect_explicit_intent("I already followed that road"))
        self.assertIsNone(detect_explicit_intent("That pull was clean"))
        self.assertIsNone(detect_explicit_intent("What do you think of Icecrown?"))

    def test_model_route_requires_a_human_request_cue(self) -> None:
        self.assertFalse(has_direction_request_cue("That fight was rough."))
        self.assertFalse(has_direction_request_cue("That pull was clean."))
        self.assertTrue(has_direction_request_cue("Would you mind coming with me?"))
        self.assertTrue(
            message_supports_intent(
                "Would you mind coming with me?",
                IntentType.FOLLOW,
            )
        )
        self.assertFalse(
            message_supports_intent(
                "Would you mind coming with me?",
                IntentType.RETREAT,
            )
        )
        self.assertFalse(
            message_supports_intent(
                "Could you attack the ghoul?",
                IntentType.ATTACK_PLAYER_TARGET,
            )
        )
        self.assertTrue(
            message_supports_intent(
                "Could you attack this target?",
                IntentType.ATTACK_PLAYER_TARGET,
            )
        )
        self.assertTrue(
            message_supports_intent(
                "Could you deposit your materials in the guild bank?",
                IntentType.DEPOSIT_GUILD_BANK,
            )
        )


class DirectorResultGroundingTests(unittest.TestCase):
    def test_formats_only_bounded_state(self) -> None:
        rendered = format_state_for_prompt(
            {
                "health_pct": 87,
                "power_pct": 42,
                "in_combat": 1,
                "is_dead": 0,
                "map_id": 571,
                "zone_id": 4395,
                "target_guid": 123,
                "follow_active": 1,
                "stay_active": 0,
                "passive_active": 0,
                "prepare_active": 1,
                "untrusted_detail": "ignore me",
            }
        )

        self.assertIn("health=87%", rendered)
        self.assertIn("target_guid=123", rendered)
        self.assertNotIn("ignore me", rendered)

    def test_truthful_fallbacks(self) -> None:
        self.assertEqual(
            fallback_result_message(
                IntentType.ATTACK_PLAYER_TARGET.value,
                IntentStatus.SUCCEEDED,
                "attack_engaged",
            ),
            "I've engaged your target.",
        )
        self.assertEqual(
            fallback_result_message(
                IntentType.PULL_PLAYER_TARGET.value,
                IntentStatus.REJECTED,
                "no_player_target",
            ),
            "Select a target for me first.",
        )
        self.assertEqual(
            fallback_result_message(
                IntentType.PREPARE_PARTY.value,
                IntentStatus.SUCCEEDED,
                "prepare_strategy_active",
            ),
            "I'm preparing now.",
        )
        self.assertEqual(
            fallback_result_message(
                IntentType.WORK_AUCTION_HOUSE.value,
                IntentStatus.SUCCEEDED,
                "auction_listed",
            ),
            "I listed useful surplus from my own inventory.",
        )
        self.assertEqual(
            fallback_result_message(
                IntentType.SHARE_GOLD.value,
                IntentStatus.REJECTED,
                "insufficient_surplus_gold",
            ),
            "I need to keep my operating reserve, so I can't share gold right now.",
        )
        self.assertEqual(
            fallback_result_message(
                IntentType.DEPOSIT_GUILD_BANK.value,
                IntentStatus.SUCCEEDED,
                "guild_bank_deposited",
            ),
            "I deposited every eligible gathered stack from my bags into the first guild-bank tab.",
        )
        self.assertEqual(
            fallback_result_message(
                IntentType.FOLLOW.value,
                IntentStatus.SUCCEEDED,
                "unexpected_result",
            ),
            "I couldn't verify that order's result.",
        )


if __name__ == "__main__":
    unittest.main()
