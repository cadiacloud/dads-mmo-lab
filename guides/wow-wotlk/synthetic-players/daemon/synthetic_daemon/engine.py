"""Core cognitive loop for Synthetic Players Daemon."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional
from .action_intent import capability_prompt_hint, detect_explicit_action
from .config import DaemonSettings
from .db import DatabaseManager
from .director import (
    DirectorIntent,
    IntentType,
    detect_explicit_intent,
    fallback_result_message,
    format_state_for_prompt,
    has_direction_request_cue,
    message_supports_intent,
)
from .llm_client import SyntheticLLMClient
from .inventory import (
    contains_unverified_inventory_claim,
    is_inventory_query,
    render_inventory_response,
)
from .memory import MemoryManager
from .persona import PersonaManager

logger = logging.getLogger(__name__)


class SyntheticEngine:
    """Orchestrates event intake, persona grounding, LLM inference, and in-game delivery."""

    def __init__(self, settings: DaemonSettings) -> None:
        self.settings = settings
        self.db = DatabaseManager(settings.db)
        self.llm = SyntheticLLMClient(settings.llm)
        self.persona_mgr = PersonaManager(personas_file=settings.personas_file)
        self.memory_mgr = MemoryManager()
        self.controlled_personas = {name.casefold() for name in settings.controlled_personas}
        self.is_running = False

    async def start(self) -> None:
        """Start daemon background loop."""
        self.is_running = True
        await self.db.connect()

        bindings = await self.db.list_persona_bindings()
        controlled_bindings = [
            binding
            for binding in bindings
            if binding["persona_name"].casefold() in self.controlled_personas
        ]
        invalid_bindings = [
            binding
            for binding in controlled_bindings
            if binding["persona_name"].lower() != binding["current_name"].lower()
            or binding["race_id"] != binding["current_race"]
            or binding["class_id"] != binding["current_class"]
            or binding["gender_id"] != binding["current_gender"]
        ]
        if invalid_bindings:
            invalid_names = ", ".join(binding["persona_name"] for binding in invalid_bindings)
            raise RuntimeError(f"Invalid canonical persona binding(s): {invalid_names}")
        missing_bindings = self.controlled_personas - {
            binding["persona_name"].casefold() for binding in controlled_bindings
        }
        if missing_bindings:
            raise RuntimeError(
                "Missing canonical persona binding(s): " + ", ".join(sorted(missing_bindings))
            )
        if controlled_bindings:
            logger.info(
                "Validated %d canonical persona bindings: %s",
                len(controlled_bindings),
                ", ".join(binding["persona_name"] for binding in controlled_bindings),
            )

        # Check LLM connectivity
        is_llm_online = await self.llm.health_check()
        if is_llm_online:
            logger.info("vLLM / LLM backend is ONLINE at %s (Model: %s)", self.settings.llm.api_base, self.settings.llm.model)
        else:
            logger.warning("vLLM / LLM backend not reachable at %s. Will keep retrying on events.", self.settings.llm.api_base)

        logger.info("Synthetic Players Daemon started successfully. Polling every %dms...", self.settings.poll_interval_ms)

        while self.is_running:
            try:
                await self.tick()
            except Exception as e:
                logger.error("Error during synthetic engine tick: %s", e, exc_info=True)

            await asyncio.sleep(self.settings.poll_interval_ms / 1000.0)

    async def stop(self) -> None:
        """Stop daemon loop and cleanup resources."""
        self.is_running = False
        await self.llm.close()
        await self.db.close()
        logger.info("Synthetic Players Daemon stopped.")

    async def tick(self) -> None:
        """Process one batch of pending inbox events."""
        if self.settings.director.enabled:
            await self.process_intent_results()

        events = await self.db.fetch_pending_inbox(limit=self.settings.max_batch_size)
        if not events:
            return

        for event in events:
            try:
                await self.process_event(event)
                await self.db.mark_inbox_status(event["id"], status=2) # Processed
            except Exception as e:
                logger.error("Failed to process event #%d: %s", event["id"], e, exc_info=True)
                await self.db.mark_inbox_status(event["id"], status=3) # Failed

    async def process_event(self, event: Dict[str, Any]) -> None:
        """Process a single in-game event or chat message."""
        event_type = event.get("event_type", "CHAT_WHISPER")
        sender_name = event.get("sender_name", "Player")
        sender_guid = event.get("sender_guid", 0)
        target_name = event.get("target_name", "")
        raw_msg = event.get("raw_message", "").strip()
        zone_name = event.get("zone_name", "Azeroth")

        # Determine which bot should respond
        bot_name = target_name
        if not bot_name and "@" in raw_msg:
            # Extract @BotName mention
            match = re.search(r"@(\w+)", raw_msg)
            if match:
                bot_name = match.group(1)

        if not bot_name:
            # The bridge normally supplies a concrete target; use the configured
            # first persona only for legacy/broadcast rows that predate that rule.
            bot_name = self.settings.controlled_personas[0]

        if bot_name.casefold() not in self.controlled_personas:
            logger.info("Ignoring non-controlled Playerbot target: %s", bot_name)
            return

        binding = await self.db.get_persona_binding(bot_name)
        if not binding:
            raise ValueError(f"No canonical Playerbot binding exists for controlled persona {bot_name}")
        event_target_guid = int(event.get("target_guid") or 0)
        if event_target_guid != int(binding["character_guid"]):
            raise ValueError(
                f"Persona binding mismatch for {bot_name}: "
                f"event target {event_target_guid}, expected {binding['character_guid']}"
            )
        if binding["current_name"].casefold() != bot_name.casefold():
            raise ValueError(f"Bound character name mismatch for persona {bot_name}")

        # Fetch persona
        db_persona = await self.db.get_persona(bot_name)
        persona = self.persona_mgr.get_or_create_persona(
            bot_name=bot_name,
            class_id=event.get("target_class", 1),
            race_id=event.get("target_race", 1),
            db_persona=db_persona,
        )

        # Retrieve relevant memories
        memories = await self.db.get_recent_memories(player_name=sender_name, bot_name=bot_name, limit=3)
        bot_state = await self.db.get_bot_state(int(event.get("target_guid") or 0))

        # Build system prompt and message history
        system_prompt = self.persona_mgr.build_system_prompt(persona, current_zone=zone_name, memories=memories)
        history = self.memory_mgr.get_history(player_name=sender_name, bot_name=bot_name)

        routed_action = None
        routed_intent: Optional[IntentType] = None
        is_chat_event = event_type.startswith("CHAT_")
        if is_chat_event:
            routed_action = detect_explicit_action(
                raw_msg,
                int(event.get("target_class") or 0),
            )
            if not routed_action and self.settings.director.enabled:
                routed_intent = detect_explicit_intent(raw_msg)

        # Format user prompt based on event type
        if is_chat_event:
            clean_user_prompt = f"[{sender_name} in {zone_name}]: {raw_msg}"
        elif event_type == "EVENT_KILL_BOSS":
            clean_user_prompt = f"[World Event]: {sender_name}'s party defeated an elite boss! ({raw_msg}). Give a short in-character battle cheer or remark."
        elif event_type == "EVENT_DEATH":
            clean_user_prompt = f"[World Event]: {sender_name} just died! ({raw_msg}). Offer a brief in-character reaction or encourage them."
        elif event_type == "EVENT_LEVEL_UP":
            clean_user_prompt = f"[World Event]: {sender_name} leveled up! ({raw_msg}). Congratulate them in character."
        else:
            clean_user_prompt = f"[{event_type}]: {raw_msg}"

        if routed_action:
            clean_user_prompt = f"{clean_user_prompt}\n{capability_prompt_hint(routed_action)}"

        if bot_state:
            clean_user_prompt = f"{clean_user_prompt}\n{format_state_for_prompt(bot_state)}"

        self.memory_mgr.add_user_turn(sender_name, bot_name, clean_user_prompt)
        if is_chat_event and not routed_action and not routed_intent and is_inventory_query(raw_msg):
            inventory = await self.db.get_bot_inventory(int(event.get("target_guid") or 0))
            grounded_reply = render_inventory_response(bot_name, raw_msg, inventory)
            self.memory_mgr.add_assistant_turn(sender_name, bot_name, grounded_reply)
            await self.db.insert_outbox(
                inbox_id=event["id"],
                bot_guid=event.get("target_guid", 0),
                bot_name=bot_name,
                target_guid=sender_guid,
                target_name=sender_name,
                channel_type=self._channel_for_event(event_type),
                message=grounded_reply,
                action_command=None,
            )
            logger.info("Rendered authoritative inventory reply [%s -> %s]", bot_name, sender_name)
            return

        if routed_intent:
            await self._queue_director_intent(
                event=event,
                issuer_guid=sender_guid,
                issuer_name=sender_name,
                bot_name=bot_name,
                intent_type=routed_intent,
            )
            return

        # Call LLM
        response = await self.llm.generate_response(
            system_prompt=system_prompt,
            messages_history=history,
            user_message=clean_user_prompt,
        )
        if routed_action:
            response.action_command = routed_action
            response.intent_type = None
            response.control_tag_rejected = False
        elif response.intent_type and (
            not self.settings.director.enabled
            or not is_chat_event
            or not has_direction_request_cue(raw_msg)
            or not message_supports_intent(raw_msg, response.intent_type)
        ):
            response.intent_type = None
            response.control_tag_rejected = True

        if response.control_tag_rejected:
            response.action_command = None
            # A rejected control tag must never erase otherwise valid persona
            # dialogue. Models occasionally append an unsolicited or malformed
            # intent to ordinary conversation; the control is unsafe, but the
            # tag-free dialogue is still the desired reply. For an actual order
            # whose control could not be validated, do not relay text that may
            # falsely claim the order was executed.
            if is_chat_event and has_direction_request_cue(raw_msg):
                response.content = (
                    "I heard you, but I couldn't carry out that order as phrased. "
                    "Try a more specific command."
                )
            elif not response.content.strip():
                response.content = "I didn't catch that. Say it again?"

        if contains_unverified_inventory_claim(response.content):
            logger.warning("Blocked ungrounded inventory claim from persona %s", bot_name)
            response.content = (
                "I can't verify what is in my bags from conversation alone. "
                "Ask me what I have and I'll check the live inventory."
            )

        logger.info(
            "Generated reply [%s -> %s] in %.1fms: %s %s",
            bot_name,
            sender_name,
            response.latency_ms,
            response.content,
            (
                f"(Action: {response.action_command})"
                if response.action_command
                else f"(Intent: {response.intent_type.value})"
                if response.intent_type
                else ""
            ),
        )

        if response.intent_type:
            await self._queue_director_intent(
                event=event,
                issuer_guid=sender_guid,
                issuer_name=sender_name,
                bot_name=bot_name,
                intent_type=response.intent_type,
            )
            return

        self.memory_mgr.add_assistant_turn(sender_name, bot_name, response.content)

        # Check if conversation warrants saving a long term memory
        if event_type in ("EVENT_KILL_BOSS", "EVENT_DEATH", "EVENT_LEVEL_UP") or len(raw_msg) > 60:
            memory_summary = f"{sender_name} and {bot_name}: {raw_msg} -> {response.content}"
            await self.db.save_memory(sender_name, bot_name, event_type, memory_summary, importance=7)

        # Determine outbox channel
        channel_type = "WHISPER"
        if event_type == "CHAT_PARTY":
            channel_type = "PARTY"
        elif event_type == "CHAT_GUILD":
            channel_type = "GUILD"
        elif event_type == "CHAT_SAY":
            channel_type = "SAY"

        # Write to outbox
        await self.db.insert_outbox(
            inbox_id=event["id"],
            bot_guid=event.get("target_guid", 0),
            bot_name=bot_name,
            target_guid=sender_guid,
            target_name=sender_name,
            channel_type=channel_type,
            message=response.content,
            action_command=response.action_command,
        )

    async def _queue_director_intent(
        self,
        event: Dict[str, Any],
        issuer_guid: int,
        issuer_name: str,
        bot_name: str,
        intent_type: IntentType,
    ) -> None:
        """Persist one validated enum without requiring persona inference."""
        intent = DirectorIntent(
            intent_type=intent_type,
            expires_in_seconds=self.settings.director.intent_ttl_seconds,
        )
        intent_id = await self.db.insert_intent(
            inbox_id=event["id"],
            issuer_guid=issuer_guid,
            issuer_name=issuer_name,
            bot_guid=int(event.get("target_guid") or 0),
            bot_name=bot_name,
            intent_type=intent.intent_type.value,
            parameters=intent.parameters,
            expires_in_seconds=intent.expires_in_seconds,
        )
        if not intent_id:
            raise RuntimeError("Failed to persist director intent")
        logger.info(
            "Queued director intent #%d [%s -> %s]: %s",
            intent_id,
            issuer_name,
            bot_name,
            intent.intent_type.value,
        )

    async def process_intent_results(self) -> None:
        """Publish only deterministic, worldserver-verified intent outcomes."""
        intents = await self.db.fetch_reportable_intents(limit=self.settings.director.result_batch_size)
        for intent in intents:
            bot_name = intent["bot_name"]
            if bot_name.casefold() not in self.controlled_personas:
                logger.warning("Refusing to report intent for non-controlled Playerbot: %s", bot_name)
                continue
            player_name = intent["issuer_name"]
            message = fallback_result_message(
                intent_type=intent["intent_type"],
                status=int(intent["status"]),
                result_code=intent.get("result_code") or "",
            )

            channel_type = self._channel_for_event(intent.get("event_type") or "CHAT_WHISPER")
            outbox_id = await self.db.insert_intent_result_outbox(intent, channel_type, message)
            if not outbox_id:
                logger.debug("Director intent #%d was already reported by another worker", intent["id"])
                continue
            self.memory_mgr.add_assistant_turn(player_name, bot_name, message)
            await self.db.save_memory(
                player_name,
                bot_name,
                "DIRECTOR_INTENT",
                (
                    f"{intent['intent_type']} -> {intent.get('result_code') or 'unknown'}; "
                    f"{bot_name}: {message}"
                ),
                importance=6,
            )
            logger.info(
                "Reported director intent #%d as status %d (%s)",
                intent["id"],
                intent["status"],
                intent.get("result_code") or "unknown",
            )

    @staticmethod
    def _channel_for_event(event_type: str) -> str:
        """Map an inbox event to the matching in-game result channel."""
        return {
            "CHAT_PARTY": "PARTY",
            "CHAT_GUILD": "GUILD",
            "CHAT_SAY": "SAY",
        }.get(event_type, "WHISPER")
