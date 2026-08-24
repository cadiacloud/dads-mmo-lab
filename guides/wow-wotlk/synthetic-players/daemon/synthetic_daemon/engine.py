"""Core cognitive loop for Synthetic Players Daemon."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional
from .action_intent import capability_prompt_hint, detect_explicit_action
from .config import DaemonSettings
from .db import DatabaseManager
from .llm_client import SyntheticLLMClient
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
        self.is_running = False

    async def start(self) -> None:
        """Start daemon background loop."""
        self.is_running = True
        await self.db.connect()

        bindings = await self.db.list_persona_bindings()
        invalid_bindings = [
            binding
            for binding in bindings
            if binding["persona_name"].lower() != binding["current_name"].lower()
            or binding["race_id"] != binding["current_race"]
            or binding["class_id"] != binding["current_class"]
            or binding["gender_id"] != binding["current_gender"]
        ]
        if invalid_bindings:
            invalid_names = ", ".join(binding["persona_name"] for binding in invalid_bindings)
            raise RuntimeError(f"Invalid canonical persona binding(s): {invalid_names}")
        if bindings:
            logger.info(
                "Validated %d canonical persona bindings: %s",
                len(bindings),
                ", ".join(binding["persona_name"] for binding in bindings),
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
            # For party/guild broadcast events without specific target, pick a default persona
            bot_name = "Brog"

        binding = await self.db.get_persona_binding(bot_name)
        if binding:
            event_target_guid = int(event.get("target_guid") or 0)
            if event_target_guid != int(binding["character_guid"]):
                raise ValueError(
                    f"Persona binding mismatch for {bot_name}: "
                    f"event target {event_target_guid}, expected {binding['character_guid']}"
                )
            if binding["current_name"].lower() != bot_name.lower():
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

        # Build system prompt and message history
        system_prompt = self.persona_mgr.build_system_prompt(persona, current_zone=zone_name, memories=memories)
        history = self.memory_mgr.get_history(player_name=sender_name, bot_name=bot_name)

        routed_action = None
        if event_type.startswith("CHAT_"):
            routed_action = detect_explicit_action(
                raw_msg,
                int(event.get("target_class") or 0),
            )

        # Format user prompt based on event type
        if event_type.startswith("CHAT_"):
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

        # Call LLM
        response = await self.llm.generate_response(
            system_prompt=system_prompt,
            messages_history=history,
            user_message=clean_user_prompt,
        )
        if routed_action:
            response.action_command = routed_action

        logger.info(
            "Generated reply [%s -> %s] in %.1fms: %s %s",
            bot_name,
            sender_name,
            response.latency_ms,
            response.content,
            f"(Action: {response.action_command})" if response.action_command else "",
        )

        # Update short term memory
        self.memory_mgr.add_user_turn(sender_name, bot_name, clean_user_prompt)
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
