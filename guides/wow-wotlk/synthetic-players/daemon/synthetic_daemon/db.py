"""Async Database layer for Synthetic Players Daemon."""

from __future__ import annotations

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
