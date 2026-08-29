import unittest
from unittest.mock import AsyncMock

from synthetic_daemon.config import DaemonSettings
from synthetic_daemon.director import IntentStatus, IntentType
from synthetic_daemon.engine import SyntheticEngine
from synthetic_daemon.llm_client import LLMResponse


class DirectorEngineFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.engine = SyntheticEngine(DaemonSettings())
        self.engine.db = AsyncMock()
        self.engine.llm = AsyncMock()
        self.engine.db.get_persona_binding.return_value = {
            "character_guid": 101,
            "current_name": "Lyra",
        }
        self.engine.db.get_persona.return_value = None
        self.engine.db.get_recent_memories.return_value = []
        self.engine.db.get_bot_state.return_value = None
        self.engine.db.get_bot_inventory.return_value = None

    async def test_gameplay_order_queues_intent_without_unverified_dialogue(self) -> None:
        self.engine.llm.generate_response.return_value = LLMResponse(
            content="Right behind you.",
            intent_type=IntentType.FOLLOW,
            latency_ms=12.0,
        )
        self.engine.db.insert_intent.return_value = 77
        event = {
            "id": 9,
            "event_type": "CHAT_WHISPER",
            "sender_guid": 501,
            "sender_name": "Michael",
            "target_guid": 101,
            "target_name": "Lyra",
            "target_class": 8,
            "target_race": 10,
            "raw_message": "Lyra, follow me",
            "zone_name": "Icecrown",
        }

        await self.engine.process_event(event)

        self.engine.db.insert_intent.assert_awaited_once()
        queued = self.engine.db.insert_intent.await_args.kwargs
        self.assertEqual(queued["intent_type"], IntentType.FOLLOW.value)
        self.engine.db.insert_outbox.assert_not_awaited()
        self.engine.llm.generate_response.assert_not_awaited()

    async def test_non_controlled_playerbot_never_enters_model_pipeline(self) -> None:
        event = {
            "id": 99,
            "event_type": "CHAT_WHISPER",
            "sender_guid": 501,
            "sender_name": "Michael",
            "target_guid": 61,
            "target_name": "Brog",
            "target_class": 1,
            "target_race": 2,
            "raw_message": "Brog, follow me",
            "zone_name": "Icecrown",
        }

        await self.engine.process_event(event)

        self.engine.db.get_persona_binding.assert_not_awaited()
        self.engine.db.insert_intent.assert_not_awaited()
        self.engine.db.insert_outbox.assert_not_awaited()
        self.engine.llm.generate_response.assert_not_awaited()

    async def test_world_event_cannot_enqueue_model_generated_intent(self) -> None:
        self.engine.llm.generate_response.return_value = LLMResponse(
            content="Back to the fight!",
            intent_type=IntentType.ATTACK_PLAYER_TARGET,
            latency_ms=12.0,
        )
        event = {
            "id": 10,
            "event_type": "EVENT_DEATH",
            "sender_guid": 501,
            "sender_name": "Michael",
            "target_guid": 101,
            "target_name": "Lyra",
            "target_class": 8,
            "target_race": 10,
            "raw_message": "Died to: Ghoul",
            "zone_name": "Icecrown",
        }

        await self.engine.process_event(event)

        self.engine.db.insert_intent.assert_not_awaited()
        self.engine.db.insert_outbox.assert_awaited_once()
        sent = self.engine.db.insert_outbox.await_args.kwargs
        self.assertEqual(sent["message"], "Back to the fight!")

    async def test_natural_request_can_queue_semantically_matching_model_intent(self) -> None:
        self.engine.llm.generate_response.return_value = LLMResponse(
            content="I'm with you.",
            intent_type=IntentType.FOLLOW,
            latency_ms=12.0,
        )
        self.engine.db.insert_intent.return_value = 78
        event = {
            "id": 12,
            "event_type": "CHAT_WHISPER",
            "sender_guid": 501,
            "sender_name": "Michael",
            "target_guid": 101,
            "target_name": "Lyra",
            "target_class": 8,
            "target_race": 10,
            "raw_message": "Could you stick with me?",
            "zone_name": "Icecrown",
        }

        await self.engine.process_event(event)

        queued = self.engine.db.insert_intent.await_args.kwargs
        self.assertEqual(queued["intent_type"], IntentType.FOLLOW.value)
        self.engine.db.insert_outbox.assert_not_awaited()

    async def test_model_intent_must_match_the_request_semantics(self) -> None:
        self.engine.llm.generate_response.return_value = LLMResponse(
            content="I'm with you.",
            intent_type=IntentType.RETREAT,
            latency_ms=12.0,
        )
        event = {
            "id": 13,
            "event_type": "CHAT_WHISPER",
            "sender_guid": 501,
            "sender_name": "Michael",
            "target_guid": 101,
            "target_name": "Lyra",
            "target_class": 8,
            "target_race": 10,
            "raw_message": "Could you stick with me?",
            "zone_name": "Icecrown",
        }

        await self.engine.process_event(event)

        self.engine.db.insert_intent.assert_not_awaited()
        self.engine.db.insert_outbox.assert_awaited_once()
        sent = self.engine.db.insert_outbox.await_args.kwargs
        self.assertEqual(
            sent["message"],
            "I heard you, but I couldn't carry out that order as phrased. "
            "Try a more specific command.",
        )

    async def test_casual_chat_cannot_enqueue_model_generated_intent(self) -> None:
        self.engine.llm.generate_response.return_value = LLMResponse(
            content="It certainly was.",
            intent_type=IntentType.RETREAT,
            latency_ms=12.0,
        )
        event = {
            "id": 11,
            "event_type": "CHAT_WHISPER",
            "sender_guid": 501,
            "sender_name": "Michael",
            "target_guid": 101,
            "target_name": "Lyra",
            "target_class": 8,
            "target_race": 10,
            "raw_message": "That fight was rough.",
            "zone_name": "Icecrown",
        }

        await self.engine.process_event(event)

        self.engine.db.insert_intent.assert_not_awaited()
        self.engine.db.insert_outbox.assert_awaited_once()
        sent = self.engine.db.insert_outbox.await_args.kwargs
        self.assertEqual(sent["message"], "It certainly was.")

    async def test_unsolicited_invalid_control_tag_does_not_erase_persona_dialogue(self) -> None:
        self.engine.llm.generate_response.return_value = LLMResponse(
            content="I've gathered twelve pieces so far.",
            control_tag_rejected=True,
            latency_ms=12.0,
        )
        event = {
            "id": 14,
            "event_type": "CHAT_WHISPER",
            "sender_guid": 501,
            "sender_name": "Michael",
            "target_guid": 101,
            "target_name": "Lyra",
            "target_class": 8,
            "target_race": 10,
            "raw_message": "That was quite a haul today.",
            "zone_name": "Durotar",
        }

        await self.engine.process_event(event)

        self.engine.db.insert_intent.assert_not_awaited()
        sent = self.engine.db.insert_outbox.await_args.kwargs
        self.assertEqual(sent["message"], "I've gathered twelve pieces so far.")

    async def test_empty_rejected_control_tag_gets_non_repetitive_retry_prompt(self) -> None:
        self.engine.llm.generate_response.return_value = LLMResponse(
            content="",
            control_tag_rejected=True,
            latency_ms=12.0,
        )
        event = {
            "id": 15,
            "event_type": "CHAT_WHISPER",
            "sender_guid": 501,
            "sender_name": "Michael",
            "target_guid": 101,
            "target_name": "Lyra",
            "target_class": 8,
            "target_race": 10,
            "raw_message": "Did that make sense?",
            "zone_name": "Durotar",
        }

        await self.engine.process_event(event)

        sent = self.engine.db.insert_outbox.await_args.kwargs
        self.assertEqual(sent["message"], "I didn't catch that. Say it again?")

    async def test_inventory_question_bypasses_model_and_uses_live_snapshot(self) -> None:
        self.engine.db.get_bot_inventory.return_value = {
            "age_seconds": 1,
            "money_copper": 0,
            "free_bag_slots": 5,
            "bags": [
                {"entry": 2770, "count": 12, "name": "Copper Ore", "class": 7, "subclass": 7},
            ],
            "equipment": [],
        }
        event = {
            "id": 16,
            "event_type": "CHAT_WHISPER",
            "sender_guid": 501,
            "sender_name": "Michael",
            "target_guid": 101,
            "target_name": "Lyra",
            "target_class": 8,
            "target_race": 10,
            "raw_message": "How much copper ore do you have?",
            "zone_name": "Durotar",
        }

        await self.engine.process_event(event)

        self.engine.llm.generate_response.assert_not_awaited()
        sent = self.engine.db.insert_outbox.await_args.kwargs
        self.assertEqual(sent["message"], "Verified 'copper ore': Copper Ore x12.")

    async def test_model_inventory_claim_is_blocked_outside_inventory_route(self) -> None:
        self.engine.llm.generate_response.return_value = LLMResponse(
            content="I've got a stash of arcane crystals and silk.",
            latency_ms=12.0,
        )
        event = {
            "id": 17,
            "event_type": "CHAT_WHISPER",
            "sender_guid": 501,
            "sender_name": "Michael",
            "target_guid": 101,
            "target_name": "Lyra",
            "target_class": 8,
            "target_race": 10,
            "raw_message": "What are your plans today?",
            "zone_name": "Durotar",
        }

        await self.engine.process_event(event)

        sent = self.engine.db.insert_outbox.await_args.kwargs
        self.assertEqual(
            sent["message"],
            "I can't verify what is in my bags from conversation alone. "
            "Ask me what I have and I'll check the live inventory.",
        )

    async def test_terminal_result_produces_result_grounded_dialogue(self) -> None:
        self.engine.db.insert_intent_result_outbox.return_value = 88
        self.engine.db.fetch_reportable_intents.return_value = [
            {
                "id": 77,
                "inbox_id": 9,
                "issuer_guid": 501,
                "issuer_name": "Michael",
                "bot_guid": 101,
                "bot_name": "Lyra",
                "intent_type": IntentType.FOLLOW.value,
                "status": IntentStatus.SUCCEEDED,
                "result_code": "follow_strategy_active",
                "event_type": "CHAT_WHISPER",
                "zone_name": "Icecrown",
                "target_class": 1,
                "target_race": 2,
                "follow_active": 1,
            }
        ]
        await self.engine.process_intent_results()

        self.engine.db.insert_intent_result_outbox.assert_awaited_once()
        reported = self.engine.db.insert_intent_result_outbox.await_args.args
        self.assertEqual(reported[1], "WHISPER")
        self.assertEqual(reported[2], "Following.")
        self.engine.llm.generate_response.assert_not_awaited()
        self.engine.db.save_memory.assert_awaited_once()

    async def test_already_reported_result_does_not_duplicate_memory(self) -> None:
        self.engine.db.insert_intent_result_outbox.return_value = 0
        self.engine.db.fetch_reportable_intents.return_value = [
            {
                "id": 77,
                "inbox_id": 9,
                "issuer_guid": 501,
                "issuer_name": "Michael",
                "bot_guid": 101,
                "bot_name": "Lyra",
                "intent_type": IntentType.FOLLOW.value,
                "status": IntentStatus.SUCCEEDED,
                "result_code": "follow_strategy_active",
                "event_type": "CHAT_WHISPER",
            }
        ]

        await self.engine.process_intent_results()

        self.engine.db.insert_intent_result_outbox.assert_awaited_once()
        self.engine.db.save_memory.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
