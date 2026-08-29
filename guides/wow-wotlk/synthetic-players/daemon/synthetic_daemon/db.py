"""Async Database layer for Synthetic Players Daemon."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
import aiomysql
from .config import DatabaseConfig

logger = logging.getLogger(__name__)

INIT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS `synthetic_inbox` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `event_type` VARCHAR(32) NOT NULL,
    `sender_guid` BIGINT UNSIGNED NOT NULL,
    `sender_name` VARCHAR(64) NOT NULL,
    `sender_class` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `sender_race` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `sender_level` TINYINT UNSIGNED NOT NULL DEFAULT 1,
    `target_guid` BIGINT UNSIGNED DEFAULT 0,
    `target_name` VARCHAR(64) DEFAULT '',
    `target_class` TINYINT UNSIGNED DEFAULT 0,
    `target_race` TINYINT UNSIGNED DEFAULT 0,
    `target_level` TINYINT UNSIGNED DEFAULT 1,
    `zone_id` INT UNSIGNED DEFAULT 0,
    `zone_name` VARCHAR(128) DEFAULT '',
    `raw_message` TEXT NOT NULL,
    `status` TINYINT NOT NULL DEFAULT 0,
    PRIMARY KEY (`id`),
    INDEX `idx_status_created` (`status`, `created_at`),
    INDEX `idx_target_name` (`target_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_outbox` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `inbox_id` BIGINT UNSIGNED DEFAULT NULL,
    `bot_guid` BIGINT UNSIGNED DEFAULT 0,
    `bot_name` VARCHAR(64) NOT NULL,
    `target_guid` BIGINT UNSIGNED DEFAULT 0,
    `target_name` VARCHAR(64) DEFAULT '',
    `channel_type` VARCHAR(32) NOT NULL DEFAULT 'WHISPER',
    `message` TEXT NOT NULL,
    `action_command` VARCHAR(255) DEFAULT NULL,
    `status` TINYINT NOT NULL DEFAULT 0,
    PRIMARY KEY (`id`),
    INDEX `idx_status_created` (`status`, `created_at`),
    CONSTRAINT `fk_synthetic_outbox_inbox` FOREIGN KEY (`inbox_id`) REFERENCES `synthetic_inbox` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_bot_personas` (
    `bot_name` VARCHAR(64) NOT NULL,
    `class_name` VARCHAR(32) DEFAULT '',
    `race_name` VARCHAR(32) DEFAULT '',
    `personality_traits` TEXT,
    `speech_style` TEXT,
    `backstory` TEXT,
    `custom_system_prompt` TEXT,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`bot_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_action_audit` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `outbox_id` BIGINT UNSIGNED NOT NULL,
    `bot_guid` BIGINT UNSIGNED NOT NULL,
    `bot_name` VARCHAR(64) NOT NULL,
    `requested_action` VARCHAR(255) NOT NULL,
    `outcome` VARCHAR(16) NOT NULL,
    `result_code` VARCHAR(128) NOT NULL,
    PRIMARY KEY (`id`),
    INDEX `idx_synthetic_action_outbox` (`outbox_id`),
    INDEX `idx_synthetic_action_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_persona_bindings` (
    `persona_name` VARCHAR(64) NOT NULL,
    `character_guid` INT UNSIGNED NOT NULL,
    `original_name` VARCHAR(12) NOT NULL,
    `race_id` TINYINT UNSIGNED NOT NULL,
    `class_id` TINYINT UNSIGNED NOT NULL,
    `gender_id` TINYINT UNSIGNED NOT NULL,
    `bound_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`persona_name`),
    UNIQUE KEY `uq_synthetic_persona_character` (`character_guid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_command_authorities` (
    `character_guid` INT UNSIGNED NOT NULL,
    `authority_role` VARCHAR(16) NOT NULL DEFAULT 'CADIA',
    `enabled` TINYINT UNSIGNED NOT NULL DEFAULT 1,
    `authorized_by` VARCHAR(64) NOT NULL DEFAULT '',
    `authorization_note` VARCHAR(255) NOT NULL DEFAULT '',
    `authorized_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`character_guid`),
    INDEX `idx_synthetic_authority_role` (`authority_role`, `enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_progression_plans` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `approved_at` TIMESTAMP NULL DEFAULT NULL,
    `bot_guid` INT UNSIGNED NOT NULL,
    `bot_name` VARCHAR(64) NOT NULL,
    `plan_kind` VARCHAR(32) NOT NULL,
    `plan_json` TEXT NOT NULL,
    `source_urls_json` TEXT NOT NULL,
    `status` VARCHAR(16) NOT NULL DEFAULT 'candidate',
    `created_by` VARCHAR(64) NOT NULL DEFAULT 'cadia-planner',
    `approved_by` VARCHAR(64) NOT NULL DEFAULT '',
    PRIMARY KEY (`id`),
    INDEX `idx_synthetic_plan_bot` (`bot_guid`, `status`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_economy_goals` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `bot_guid` INT UNSIGNED NOT NULL,
    `bot_name` VARCHAR(64) NOT NULL,
    `goal_type` VARCHAR(32) NOT NULL,
    `parameters_json` TEXT NOT NULL,
    `status` VARCHAR(16) NOT NULL DEFAULT 'candidate',
    `requires_approval` TINYINT UNSIGNED NOT NULL DEFAULT 1,
    `result_code` VARCHAR(64) NOT NULL DEFAULT '',
    PRIMARY KEY (`id`),
    INDEX `idx_synthetic_economy_goal` (`bot_guid`, `status`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_economy_profiles` (
    `bot_guid` INT UNSIGNED NOT NULL,
    `bot_name` VARCHAR(64) NOT NULL,
    `enabled` TINYINT UNSIGNED NOT NULL DEFAULT 1,
    `auto_list` TINYINT UNSIGNED NOT NULL DEFAULT 1,
    `auto_buy` TINYINT UNSIGNED NOT NULL DEFAULT 1,
    `auto_craft` TINYINT UNSIGNED NOT NULL DEFAULT 1,
    `minimum_reserve_copper` BIGINT UNSIGNED NOT NULL DEFAULT 1000000,
    `max_spend_per_cycle_copper` BIGINT UNSIGNED NOT NULL DEFAULT 250000,
    `max_gold_gift_copper` BIGINT UNSIGNED NOT NULL DEFAULT 1000000,
    `max_owned_auctions` SMALLINT UNSIGNED NOT NULL DEFAULT 12,
    `last_cycle_at` TIMESTAMP NULL DEFAULT NULL,
    `last_result_code` VARCHAR(64) NOT NULL DEFAULT '',
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`bot_guid`),
    UNIQUE KEY `uq_synthetic_economy_profile_name` (`bot_name`),
    INDEX `idx_synthetic_economy_enabled` (`enabled`, `last_cycle_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_economy_ledger` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `bot_guid` INT UNSIGNED NOT NULL,
    `bot_name` VARCHAR(64) NOT NULL,
    `action_kind` VARCHAR(32) NOT NULL,
    `item_entry` INT UNSIGNED NOT NULL DEFAULT 0,
    `item_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `copper_delta` BIGINT NOT NULL DEFAULT 0,
    `result_code` VARCHAR(64) NOT NULL,
    PRIMARY KEY (`id`),
    INDEX `idx_synthetic_economy_ledger_bot` (`bot_guid`, `created_at`),
    INDEX `idx_synthetic_economy_ledger_action` (`action_kind`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_profession_plans` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `activated_at` TIMESTAMP NULL DEFAULT NULL,
    `completed_at` TIMESTAMP NULL DEFAULT NULL,
    `planner_model` VARCHAR(128) NOT NULL,
    `guide_version` SMALLINT UNSIGNED NOT NULL,
    `plan_json` LONGTEXT NOT NULL,
    `source_urls_json` TEXT NOT NULL,
    `status` VARCHAR(16) NOT NULL DEFAULT 'active',
    `authorized_by` VARCHAR(128) NOT NULL,
    `authorization_note` VARCHAR(255) NOT NULL,
    PRIMARY KEY (`id`),
    INDEX `idx_synthetic_profession_plan_status` (`status`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_profession_objectives` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `plan_id` BIGINT UNSIGNED NOT NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `completed_at` TIMESTAMP NULL DEFAULT NULL,
    `bot_guid` INT UNSIGNED NOT NULL,
    `bot_name` VARCHAR(64) NOT NULL,
    `profession` VARCHAR(32) NOT NULL,
    `skill_id` SMALLINT UNSIGNED NOT NULL,
    `stage_order` TINYINT UNSIGNED NOT NULL,
    `skill_from` SMALLINT UNSIGNED NOT NULL,
    `skill_to` SMALLINT UNSIGNED NOT NULL,
    `min_character_level` TINYINT UNSIGNED NOT NULL,
    `selected_zone` VARCHAR(64) NOT NULL,
    `selected_zone_id` INT UNSIGNED NOT NULL,
    `min_character_level` TINYINT UNSIGNED NOT NULL DEFAULT 1,
    `materials_json` TEXT NOT NULL,
    `tool_item_id` INT UNSIGNED NOT NULL DEFAULT 0,
    `deposit_category` VARCHAR(16) NOT NULL,
    `guild_bank_tab` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `deposit_free_slots` TINYINT UNSIGNED NOT NULL DEFAULT 6,
    `source_url` VARCHAR(512) NOT NULL,
    `status` VARCHAR(24) NOT NULL DEFAULT 'queued',
    `last_observed_skill` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    `last_result_code` VARCHAR(64) NOT NULL DEFAULT '',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_synthetic_profession_stage` (`plan_id`, `bot_guid`, `skill_id`, `stage_order`),
    INDEX `idx_synthetic_profession_active` (`status`, `bot_guid`, `skill_id`, `stage_order`),
    CONSTRAINT `fk_synthetic_profession_objective_plan` FOREIGN KEY (`plan_id`)
        REFERENCES `synthetic_profession_plans` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_profession_ledger` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `plan_id` BIGINT UNSIGNED NOT NULL,
    `objective_id` BIGINT UNSIGNED NOT NULL,
    `bot_guid` INT UNSIGNED NOT NULL,
    `bot_name` VARCHAR(64) NOT NULL,
    `profession` VARCHAR(32) NOT NULL,
    `action_kind` VARCHAR(32) NOT NULL,
    `item_entry` INT UNSIGNED NOT NULL DEFAULT 0,
    `item_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `skill_before` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    `skill_after` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    `result_code` VARCHAR(64) NOT NULL,
    PRIMARY KEY (`id`),
    INDEX `idx_synthetic_profession_ledger_bot` (`bot_guid`, `created_at`),
    INDEX `idx_synthetic_profession_ledger_plan` (`plan_id`, `objective_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_bot_routine_state` (
    `bot_guid` INT UNSIGNED NOT NULL,
    `captured_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `group_mode` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `group_guid` BIGINT UNSIGNED NOT NULL DEFAULT 0,
    `master_guid` INT UNSIGNED NOT NULL DEFAULT 0,
    `routine_kind` VARCHAR(32) NOT NULL DEFAULT 'MATERIAL_KITS',
    `routine_zone` INT UNSIGNED NOT NULL DEFAULT 0,
    `status` VARCHAR(64) NOT NULL DEFAULT 'routine_active',
    `taxi_nodes_known` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `random_events_suppressed` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (`bot_guid`),
    INDEX `idx_synthetic_routine_status` (`status`, `captured_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_material_kit_plans` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `activated_at` TIMESTAMP NULL DEFAULT NULL,
    `completed_at` TIMESTAMP NULL DEFAULT NULL,
    `planner_model` VARCHAR(128) NOT NULL,
    `catalog_version` SMALLINT UNSIGNED NOT NULL,
    `professions_json` TEXT NOT NULL,
    `assignment_json` LONGTEXT NOT NULL,
    `source_urls_json` TEXT NOT NULL,
    `status` VARCHAR(16) NOT NULL DEFAULT 'candidate',
    `authorized_by` VARCHAR(128) NOT NULL,
    `authorization_note` VARCHAR(255) NOT NULL,
    PRIMARY KEY (`id`),
    INDEX `idx_synthetic_material_plan_status` (`status`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_material_kit_targets` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `plan_id` BIGINT UNSIGNED NOT NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `completed_at` TIMESTAMP NULL DEFAULT NULL,
    `profession_key` VARCHAR(32) NOT NULL,
    `profession_name` VARCHAR(64) NOT NULL,
    `stage_order` SMALLINT UNSIGNED NOT NULL,
    `item_entry` INT UNSIGNED NOT NULL,
    `item_name` VARCHAR(128) NOT NULL,
    `required_count` INT UNSIGNED NOT NULL,
    `bank_threshold` INT UNSIGNED NOT NULL,
    `observed_bank_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `bot_guid` INT UNSIGNED NOT NULL,
    `bot_name` VARCHAR(64) NOT NULL,
    `gathering_skill_id` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    `acquisition_mode` VARCHAR(16) NOT NULL,
    `deposit_category` VARCHAR(16) NOT NULL,
    `selected_zone` VARCHAR(64) NOT NULL,
    `selected_zone_id` INT UNSIGNED NOT NULL,
    `guild_id` INT UNSIGNED NOT NULL,
    `guild_bank_tab` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `source_url` VARCHAR(512) NOT NULL,
    `status` VARCHAR(24) NOT NULL DEFAULT 'queued',
    `last_result_code` VARCHAR(64) NOT NULL DEFAULT 'planned',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_synthetic_material_target` (`plan_id`, `profession_key`, `stage_order`),
    INDEX `idx_synthetic_material_active` (`status`, `bot_guid`, `stage_order`),
    INDEX `idx_synthetic_material_item` (`guild_id`, `item_entry`),
    CONSTRAINT `fk_synthetic_material_target_plan` FOREIGN KEY (`plan_id`)
        REFERENCES `synthetic_material_kit_plans` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_material_kit_ledger` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `plan_id` BIGINT UNSIGNED NOT NULL,
    `target_id` BIGINT UNSIGNED NOT NULL,
    `bot_guid` INT UNSIGNED NOT NULL,
    `bot_name` VARCHAR(64) NOT NULL,
    `action_kind` VARCHAR(32) NOT NULL,
    `item_entry` INT UNSIGNED NOT NULL,
    `item_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `observed_bank_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `result_code` VARCHAR(64) NOT NULL,
    PRIMARY KEY (`id`),
    INDEX `idx_synthetic_material_ledger_target` (`target_id`, `created_at`),
    INDEX `idx_synthetic_material_ledger_bot` (`bot_guid`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


INSERT IGNORE INTO `synthetic_economy_profiles` (`bot_guid`, `bot_name`)
SELECT `character_guid`, `persona_name`
FROM `synthetic_persona_bindings`
WHERE LOWER(`persona_name`) IN ('lyra', 'celene', 'ray', 'browntown');

CREATE TABLE IF NOT EXISTS `synthetic_intents` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `accepted_at` TIMESTAMP NULL DEFAULT NULL,
    `completed_at` TIMESTAMP NULL DEFAULT NULL,
    `expires_at` TIMESTAMP NOT NULL,
    `inbox_id` BIGINT UNSIGNED NOT NULL,
    `issuer_guid` BIGINT UNSIGNED NOT NULL,
    `issuer_name` VARCHAR(64) NOT NULL,
    `bot_guid` BIGINT UNSIGNED NOT NULL,
    `bot_name` VARCHAR(64) NOT NULL,
    `intent_type` VARCHAR(32) NOT NULL,
    `parameters_json` TEXT NOT NULL,
    `status` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `reported_status` TINYINT UNSIGNED DEFAULT NULL,
    `result_code` VARCHAR(64) NOT NULL DEFAULT '',
    PRIMARY KEY (`id`),
    INDEX `idx_synthetic_intent_pending` (`status`, `expires_at`, `id`),
    INDEX `idx_synthetic_intent_reporting` (`reported_status`, `status`, `id`),
    INDEX `idx_synthetic_intent_bot` (`bot_guid`, `created_at`),
    CONSTRAINT `fk_synthetic_intent_inbox` FOREIGN KEY (`inbox_id`) REFERENCES `synthetic_inbox` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_intent_events` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `intent_id` BIGINT UNSIGNED NOT NULL,
    `status` TINYINT UNSIGNED NOT NULL,
    `result_code` VARCHAR(64) NOT NULL DEFAULT '',
    PRIMARY KEY (`id`),
    INDEX `idx_synthetic_intent_event` (`intent_id`, `id`),
    CONSTRAINT `fk_synthetic_intent_event` FOREIGN KEY (`intent_id`) REFERENCES `synthetic_intents` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_bot_state` (
    `bot_guid` BIGINT UNSIGNED NOT NULL,
    `captured_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `map_id` INT UNSIGNED NOT NULL DEFAULT 0,
    `zone_id` INT UNSIGNED NOT NULL DEFAULT 0,
    `position_x` FLOAT NOT NULL DEFAULT 0,
    `position_y` FLOAT NOT NULL DEFAULT 0,
    `position_z` FLOAT NOT NULL DEFAULT 0,
    `health_pct` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `power_pct` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `in_combat` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `is_dead` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `target_guid` BIGINT UNSIGNED NOT NULL DEFAULT 0,
    `target_health_pct` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `playerbot_state` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `follow_active` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `stay_active` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `passive_active` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `prepare_active` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (`bot_guid`),
    INDEX `idx_synthetic_bot_state_captured` (`captured_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_bot_inventory` (
    `bot_guid` BIGINT UNSIGNED NOT NULL,
    `captured_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `money_copper` BIGINT UNSIGNED NOT NULL DEFAULT 0,
    `free_bag_slots` SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    `bag_items_json` LONGTEXT NOT NULL,
    `equipped_items_json` LONGTEXT NOT NULL,
    PRIMARY KEY (`bot_guid`),
    INDEX `idx_synthetic_bot_inventory_captured` (`captured_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `synthetic_memories` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `player_name` VARCHAR(64) NOT NULL,
    `bot_name` VARCHAR(64) NOT NULL,
    `memory_type` VARCHAR(32) NOT NULL DEFAULT 'CONVERSATION',
    `memory_text` TEXT NOT NULL,
    `importance_score` TINYINT UNSIGNED NOT NULL DEFAULT 5,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_player_bot` (`player_name`, `bot_name`),
    INDEX `idx_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


class DatabaseManager:
    """Manages async MySQL connection pool and queries."""

    def __init__(self, config: DatabaseConfig) -> None:
        self.config = config
        self.pool: Optional[aiomysql.Pool] = None

    async def connect(self) -> None:
        """Establish database connection pool and initialize schema."""
        logger.info("Connecting to database at %s:%d/%s...", self.config.host, self.config.port, self.config.database)
        self.pool = await aiomysql.create_pool(
            host=self.config.host,
            port=self.config.port,
            user=self.config.user,
            password=self.config.password,
            db=self.config.database,
            minsize=self.config.pool_min_size,
            maxsize=self.config.pool_max_size,
            autocommit=True,
            charset="utf8mb4",
        )
        await self.init_schema()

    async def init_schema(self) -> None:
        """Ensure synthetic players tables exist."""
        if not self.pool:
            raise RuntimeError("Database pool not connected.")

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                for statement in INIT_SCHEMA_SQL.strip().split(";"):
                    stmt = statement.strip()
                    if stmt:
                        await cur.execute(stmt)
                await cur.execute(
                    "SHOW COLUMNS FROM synthetic_material_kit_targets LIKE 'min_character_level'"
                )
                if not await cur.fetchone():
                    await cur.execute(
                        "ALTER TABLE synthetic_material_kit_targets "
                        "ADD COLUMN min_character_level TINYINT UNSIGNED NOT NULL DEFAULT 1 "
                        "AFTER selected_zone_id"
                    )
        logger.info("Database schema initialized successfully.")

    async def close(self) -> None:
        """Close connection pool."""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            self.pool = None
            logger.info("Database pool closed.")

    async def fetch_pending_inbox(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetch and lock pending inbox records."""
        if not self.pool:
            return []

        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT * FROM synthetic_inbox WHERE status = 0 ORDER BY id ASC LIMIT %s;",
                    (limit,),
                )
                rows = await cur.fetchall()
                if rows:
                    ids = [r["id"] for r in rows]
                    format_strings = ",".join(["%s"] * len(ids))
                    await cur.execute(
                        f"UPDATE synthetic_inbox SET status = 1 WHERE id IN ({format_strings});",
                        ids,
                    )
                return rows or []

    async def mark_inbox_status(self, inbox_id: int, status: int) -> None:
        """Update status of an inbox record (2=Processed, 3=Failed, 4=Ignored)."""
        if not self.pool:
            return
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE synthetic_inbox SET status = %s WHERE id = %s;",
                    (status, inbox_id),
                )

    async def insert_outbox(
        self,
        inbox_id: Optional[int],
        bot_guid: int,
        bot_name: str,
        target_guid: int,
        target_name: str,
        channel_type: str,
        message: str,
        action_command: Optional[str] = None,
    ) -> int:
        """Insert generated response into outbox table for Eluna to deliver."""
        if not self.pool:
            return 0
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO synthetic_outbox
                    (inbox_id, bot_guid, bot_name, target_guid, target_name, channel_type, message, action_command, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0);
                    """,
                    (inbox_id, bot_guid, bot_name, target_guid, target_name, channel_type, message, action_command),
                )
                return cur.lastrowid or 0

    async def insert_intent(
        self,
        inbox_id: int,
        issuer_guid: int,
        issuer_name: str,
        bot_guid: int,
        bot_name: str,
        intent_type: str,
        parameters: Dict[str, Any],
        expires_in_seconds: int,
    ) -> int:
        """Queue one typed high-level intent for the trusted worldserver adapter."""
        if not self.pool:
            return 0

        parameters_json = json.dumps(parameters, separators=(",", ":"), sort_keys=True)
        async with self.pool.acquire() as conn:
            try:
                await conn.begin()
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO synthetic_intents
                        (expires_at, inbox_id, issuer_guid, issuer_name, bot_guid, bot_name,
                         intent_type, parameters_json, status)
                        VALUES (DATE_ADD(CURRENT_TIMESTAMP, INTERVAL %s SECOND), %s, %s, %s,
                                %s, %s, %s, %s, 0);
                        """,
                        (
                            expires_in_seconds,
                            inbox_id,
                            issuer_guid,
                            issuer_name,
                            bot_guid,
                            bot_name,
                            intent_type,
                            parameters_json,
                        ),
                    )
                    intent_id = cur.lastrowid or 0
                    if not intent_id:
                        raise RuntimeError("Database did not return an intent identifier")
                    await cur.execute(
                        """
                        INSERT INTO synthetic_intent_events (intent_id, status, result_code)
                        VALUES (%s, 0, 'queued');
                        """,
                        (intent_id,),
                    )
                await conn.commit()
                return intent_id
            except Exception:
                await conn.rollback()
                raise

    async def fetch_reportable_intents(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Return terminal intent outcomes that have not reached in-game dialogue."""
        if not self.pool:
            return []

        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """
                    SELECT i.id, i.inbox_id, i.issuer_guid, i.issuer_name,
                           i.bot_guid, i.bot_name, i.intent_type, i.status,
                           i.result_code, inbox.event_type, inbox.raw_message,
                           inbox.zone_name, inbox.target_class, inbox.target_race,
                           inbox.target_level, state.map_id, state.zone_id,
                           state.health_pct, state.power_pct, state.in_combat,
                           state.is_dead, state.target_guid, state.target_health_pct,
                           state.playerbot_state, state.follow_active,
                           state.stay_active, state.passive_active,
                           state.prepare_active, state.captured_at
                    FROM synthetic_intents i
                    JOIN synthetic_inbox inbox ON inbox.id = i.inbox_id
                    LEFT JOIN synthetic_bot_state state ON state.bot_guid = i.bot_guid
                    WHERE i.status IN (3, 4, 5, 6, 7)
                      AND (i.reported_status IS NULL OR i.reported_status <> i.status)
                    ORDER BY i.id ASC
                    LIMIT %s;
                    """,
                    (limit,),
                )
                return await cur.fetchall() or []

    async def insert_intent_result_outbox(
        self,
        intent: Dict[str, Any],
        channel_type: str,
        message: str,
    ) -> int:
        """Atomically publish truthful result dialogue and mark it reported."""
        if not self.pool:
            return 0

        async with self.pool.acquire() as conn:
            try:
                await conn.begin()
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE synthetic_intents
                        SET reported_status = status
                        WHERE id = %s AND status = %s
                          AND (reported_status IS NULL OR reported_status <> status);
                        """,
                        (intent["id"], intent["status"]),
                    )
                    if cur.rowcount != 1:
                        await conn.rollback()
                        return 0
                    await cur.execute(
                        """
                        INSERT INTO synthetic_outbox
                        (inbox_id, bot_guid, bot_name, target_guid, target_name,
                         channel_type, message, action_command, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, 0);
                        """,
                        (
                            intent["inbox_id"],
                            intent["bot_guid"],
                            intent["bot_name"],
                            intent["issuer_guid"],
                            intent["issuer_name"],
                            channel_type,
                            message,
                        ),
                    )
                    outbox_id = cur.lastrowid or 0
                await conn.commit()
                return outbox_id
            except Exception:
                await conn.rollback()
                raise

    async def get_bot_state(self, bot_guid: int) -> Optional[Dict[str, Any]]:
        """Return the latest bounded worldserver snapshot for one persona bot."""
        if not self.pool or not bot_guid:
            return None

        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT * FROM synthetic_bot_state WHERE bot_guid = %s LIMIT 1;",
                    (bot_guid,),
                )
                return await cur.fetchone()

    async def get_bot_inventory(self, bot_guid: int) -> Optional[Dict[str, Any]]:
        """Return an item-name-enriched live worldserver inventory snapshot."""
        if not self.pool or not bot_guid:
            return None

        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """
                    SELECT bot_guid, captured_at, money_copper, free_bag_slots,
                           bag_items_json, equipped_items_json,
                           TIMESTAMPDIFF(SECOND, captured_at, CURRENT_TIMESTAMP) AS age_seconds
                    FROM synthetic_bot_inventory
                    WHERE bot_guid = %s
                    LIMIT 1;
                    """,
                    (bot_guid,),
                )
                row = await cur.fetchone()
                if not row:
                    return None

                try:
                    bag_pairs = json.loads(row["bag_items_json"])
                    equipment_pairs = json.loads(row["equipped_items_json"])
                except (TypeError, ValueError, json.JSONDecodeError):
                    logger.warning("Invalid inventory snapshot JSON for bot %d", bot_guid)
                    return None

                counts: Dict[int, Dict[str, int]] = {}
                for location, pairs in (("bags", bag_pairs), ("equipment", equipment_pairs)):
                    if not isinstance(pairs, list):
                        return None
                    for pair in pairs:
                        if not isinstance(pair, list) or len(pair) != 2:
                            return None
                        entry, count = int(pair[0]), int(pair[1])
                        if entry <= 0 or count <= 0:
                            continue
                        record = counts.setdefault(entry, {"bags": 0, "equipment": 0})
                        record[location] += count

                metadata: Dict[int, Dict[str, Any]] = {}
                if counts:
                    entries = sorted(counts)
                    placeholders = ",".join(["%s"] * len(entries))
                    await cur.execute(
                        f"SELECT entry, name, class, subclass FROM acore_world.item_template "
                        f"WHERE entry IN ({placeholders});",
                        entries,
                    )
                    for item in await cur.fetchall():
                        metadata[int(item["entry"])] = item

                def enrich(location: str) -> List[Dict[str, Any]]:
                    items: List[Dict[str, Any]] = []
                    for entry, locations in counts.items():
                        count = locations[location]
                        if not count:
                            continue
                        item = metadata.get(entry, {})
                        items.append(
                            {
                                "entry": entry,
                                "count": count,
                                "name": item.get("name") or f"item {entry}",
                                "class": int(item.get("class") or 0),
                                "subclass": int(item.get("subclass") or 0),
                            }
                        )
                    return sorted(items, key=lambda item: (item["name"].casefold(), item["entry"]))

                return {
                    "bot_guid": int(row["bot_guid"]),
                    "captured_at": row["captured_at"],
                    "age_seconds": max(0, int(row["age_seconds"] or 0)),
                    "money_copper": int(row["money_copper"] or 0),
                    "free_bag_slots": int(row["free_bag_slots"] or 0),
                    "bags": enrich("bags"),
                    "equipment": enrich("equipment"),
                }

    async def get_persona(self, bot_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve custom bot persona from database if present."""
        if not self.pool:
            return None
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM synthetic_bot_personas WHERE bot_name = %s LIMIT 1;", (bot_name,))
                return await cur.fetchone()

    async def get_persona_binding(self, persona_name: str) -> Optional[Dict[str, Any]]:
        """Return a canonical persona binding and its current character identity."""
        if not self.pool:
            return None
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """
                    SELECT b.*, c.name AS current_name, c.race AS current_race,
                           c.class AS current_class, c.gender AS current_gender,
                           c.online AS current_online
                    FROM synthetic_persona_bindings b
                    JOIN characters c ON c.guid = b.character_guid
                    WHERE LOWER(b.persona_name) = LOWER(%s)
                    LIMIT 1;
                    """,
                    (persona_name,),
                )
                return await cur.fetchone()

    async def list_persona_bindings(self) -> List[Dict[str, Any]]:
        """List canonical bindings with their current character identities."""
        if not self.pool:
            return []
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """
                    SELECT b.*, c.name AS current_name, c.race AS current_race,
                           c.class AS current_class, c.gender AS current_gender,
                           c.online AS current_online
                    FROM synthetic_persona_bindings b
                    JOIN characters c ON c.guid = b.character_guid
                    ORDER BY b.persona_name;
                    """
                )
                return await cur.fetchall() or []

    async def list_gathering_professions(self, bot_names: List[str]) -> List[Dict[str, Any]]:
        """Return learned gathering skills for the requested canonical personas."""
        if not self.pool or not bot_names:
            return []
        placeholders = ",".join(["%s"] * len(bot_names))
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    f"""
                    SELECT b.persona_name AS bot_name, b.character_guid AS bot_guid,
                           c.level AS character_level, c.online,
                           cs.skill AS skill_id, cs.value AS current_skill,
                           cs.max AS max_skill, COALESCE(gm.guildid, 0) AS guild_id
                    FROM synthetic_persona_bindings b
                    JOIN characters c ON c.guid = b.character_guid
                    JOIN character_skills cs ON cs.guid = b.character_guid
                    LEFT JOIN guild_member gm ON gm.guid = b.character_guid
                    WHERE LOWER(b.persona_name) IN ({placeholders})
                      AND cs.skill IN (182, 186, 393)
                    ORDER BY b.persona_name, cs.skill;
                    """,
                    tuple(name.casefold() for name in bot_names),
                )
                return await cur.fetchall() or []

    async def resolve_material_item_entries(self, item_names: List[str]) -> Dict[str, int]:
        """Resolve source-catalog names against the authoritative world item table."""
        if not self.pool or not item_names:
            return {}
        names = sorted(set(item_names))
        placeholders = ",".join(["%s"] * len(names))
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    f"""
                    SELECT name, MIN(entry) AS entry
                    FROM acore_world.item_template
                    WHERE name IN ({placeholders})
                    GROUP BY name;
                    """,
                    tuple(names),
                )
                rows = await cur.fetchall() or []
                return {str(row["name"]): int(row["entry"]) for row in rows}

    async def replace_material_kit_targets(
        self,
        *,
        planner_model: str,
        catalog_version: int,
        professions: List[str],
        assignment_json: Dict[str, Any],
        source_urls: Dict[str, str],
        target_rows: List[Dict[str, Any]],
        authorized_by: str,
        authorization_note: str,
    ) -> int:
        """Activate one validated material-kit plan and its deterministic targets."""
        if not self.pool:
            raise RuntimeError("Database pool not connected")
        if not target_rows:
            raise ValueError("A material-kit plan must contain targets")

        async with self.pool.acquire() as conn:
            try:
                await conn.begin()
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE synthetic_material_kit_plans
                        SET status = 'superseded', completed_at = CURRENT_TIMESTAMP
                        WHERE status = 'active';
                        """
                    )
                    await cur.execute(
                        """
                        UPDATE synthetic_profession_plans
                        SET status = 'superseded', completed_at = CURRENT_TIMESTAMP
                        WHERE status = 'active';
                        """
                    )
                    await cur.execute(
                        """
                        UPDATE synthetic_profession_objectives
                        SET status = 'superseded', last_result_code = 'replaced_by_material_kit_plan'
                        WHERE status IN ('queued', 'active', 'waiting', 'depositing');
                        """
                    )
                    await cur.execute(
                        """
                        UPDATE synthetic_material_kit_targets t
                        JOIN synthetic_material_kit_plans p ON p.id = t.plan_id
                        SET t.status = 'superseded', t.last_result_code = 'superseded_by_new_plan'
                        WHERE p.status = 'superseded'
                          AND t.status IN ('queued', 'active', 'waiting', 'depositing');
                        """
                    )
                    await cur.execute(
                        """
                        INSERT INTO synthetic_material_kit_plans
                        (activated_at, planner_model, catalog_version, professions_json,
                         assignment_json, source_urls_json, status, authorized_by, authorization_note)
                        VALUES (CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, 'active', %s, %s);
                        """,
                        (
                            planner_model,
                            catalog_version,
                            json.dumps(professions, separators=(",", ":")),
                            json.dumps(assignment_json, separators=(",", ":"), sort_keys=True),
                            json.dumps(source_urls, separators=(",", ":"), sort_keys=True),
                            authorized_by,
                            authorization_note,
                        ),
                    )
                    plan_id = int(cur.lastrowid or 0)
                    if not plan_id:
                        raise RuntimeError("Database did not return a material-kit plan identifier")

                    for row in target_rows:
                        await cur.execute(
                            """
                            INSERT INTO synthetic_material_kit_targets
                            (plan_id, profession_key, profession_name, stage_order,
                             item_entry, item_name, required_count, bank_threshold,
                             bot_guid, bot_name, gathering_skill_id, acquisition_mode,
                             deposit_category, selected_zone, selected_zone_id, guild_id,
                             min_character_level, guild_bank_tab, source_url, status, last_result_code)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'planned');
                            """,
                            (
                                plan_id,
                                row["profession_key"],
                                row["profession_name"],
                                row["stage_order"],
                                row["item_entry"],
                                row["item_name"],
                                row["required_count"],
                                row["bank_threshold"],
                                row["bot_guid"],
                                row["bot_name"],
                                row["gathering_skill_id"],
                                row["acquisition_mode"],
                                row["deposit_category"],
                                row["selected_zone"],
                                row["selected_zone_id"],
                                row["guild_id"],
                                row["min_character_level"],
                                row["guild_bank_tab"],
                                row["source_url"],
                                row["status"],
                            ),
                        )
                await conn.commit()
                return plan_id
            except Exception:
                await conn.rollback()
                raise

    async def replace_profession_objectives(
        self,
        planner_model: str,
        guide_version: int,
        plan_json: Dict[str, Any],
        source_urls: Dict[str, str],
        assignments: List[Any],
        objective_rows: List[Dict[str, Any]],
        authorized_by: str,
        authorization_note: str,
    ) -> int:
        """Persist one validated LLM plan and activate its deterministic objectives."""
        if not self.pool:
            raise RuntimeError("Database pool not connected")
        if not assignments or not objective_rows:
            raise ValueError("A profession plan must contain assignments and objectives")

        bot_skill_pairs = sorted({(row["bot_guid"], row["skill_id"]) for row in objective_rows})
        async with self.pool.acquire() as conn:
            try:
                await conn.begin()
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO synthetic_profession_plans
                        (activated_at, planner_model, guide_version, plan_json,
                         source_urls_json, status, authorized_by, authorization_note)
                        VALUES (CURRENT_TIMESTAMP, %s, %s, %s, %s, 'active', %s, %s);
                        """,
                        (
                            planner_model,
                            guide_version,
                            json.dumps(plan_json, separators=(",", ":"), sort_keys=True),
                            json.dumps(source_urls, separators=(",", ":"), sort_keys=True),
                            authorized_by,
                            authorization_note,
                        ),
                    )
                    plan_id = cur.lastrowid or 0
                    if not plan_id:
                        raise RuntimeError("Database did not return a profession plan identifier")

                    for bot_guid, skill_id in bot_skill_pairs:
                        await cur.execute(
                            """
                            UPDATE synthetic_profession_objectives o
                            JOIN synthetic_profession_plans p ON p.id = o.plan_id
                            SET o.status = 'superseded', o.last_result_code = 'superseded_by_new_plan',
                                p.status = 'superseded', p.completed_at = CURRENT_TIMESTAMP
                            WHERE o.bot_guid = %s AND o.skill_id = %s
                              AND o.status IN ('queued', 'active', 'waiting');
                            """,
                            (bot_guid, skill_id),
                        )

                    for row in objective_rows:
                        await cur.execute(
                            """
                            INSERT INTO synthetic_profession_objectives
                            (plan_id, completed_at, bot_guid, bot_name, profession, skill_id,
                             stage_order, skill_from, skill_to, min_character_level,
                             selected_zone, selected_zone_id, materials_json, tool_item_id,
                             deposit_category, guild_bank_tab, deposit_free_slots, source_url,
                             status, last_observed_skill, last_result_code)
                            VALUES (%s, IF(%s = 'completed', CURRENT_TIMESTAMP, NULL), %s, %s,
                                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                    %s, %s, %s, %s, %s);
                            """,
                            (
                                plan_id,
                                row["status"],
                                row["bot_guid"],
                                row["bot_name"],
                                row["profession"],
                                row["skill_id"],
                                row["stage_order"],
                                row["skill_from"],
                                row["skill_to"],
                                row["min_character_level"],
                                row["selected_zone"],
                                row["selected_zone_id"],
                                row["materials_json"],
                                row["tool_item_id"],
                                row["deposit_category"],
                                row["guild_bank_tab"],
                                row["deposit_free_slots"],
                                row["source_url"],
                                row["status"],
                                row["last_observed_skill"],
                                "planned" if row["status"] != "completed" else "already_complete",
                            ),
                        )
                await conn.commit()
                return plan_id
            except Exception:
                await conn.rollback()
                raise

    async def save_memory(self, player_name: str, bot_name: str, memory_type: str, memory_text: str, importance: int = 5) -> None:
        """Persist a significant interaction or memory."""
        if not self.pool:
            return
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO synthetic_memories (player_name, bot_name, memory_type, memory_text, importance_score)
                    VALUES (%s, %s, %s, %s, %s);
                    """,
                    (player_name, bot_name, memory_type, memory_text, importance),
                )

    async def get_recent_memories(self, player_name: str, bot_name: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Retrieve recent or high-importance memories for this player/bot relationship."""
        if not self.pool:
            return []
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """
                    SELECT memory_type, memory_text, created_at
                    FROM synthetic_memories
                    WHERE player_name = %s AND bot_name = %s
                    ORDER BY importance_score DESC, id DESC LIMIT %s;
                    """,
                    (player_name, bot_name, limit),
                )
                return await cur.fetchall() or []
