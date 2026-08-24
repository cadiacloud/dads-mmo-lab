-- ============================================================================
-- Dad's MMO Lab: Synthetic Players Database Schema (ALE-Kegs)
-- Expansion: Wrath of the Lich King (3.3.5a) / AzerothCore
-- Schema Target: acore_characters
-- ============================================================================

CREATE TABLE IF NOT EXISTS `synthetic_inbox` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `event_type` VARCHAR(32) NOT NULL COMMENT 'CHAT_WHISPER, CHAT_PARTY, CHAT_SAY, CHAT_GUILD, EVENT_DEATH, EVENT_KILL_BOSS, EVENT_LEVEL_UP, EVENT_EMOTE',
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
    `status` TINYINT NOT NULL DEFAULT 0 COMMENT '0=Pending, 1=Processing, 2=Processed, 3=Failed, 4=Ignored',
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
    `channel_type` VARCHAR(32) NOT NULL DEFAULT 'WHISPER' COMMENT 'WHISPER, SAY, YELL, PARTY, GUILD, EMOTE',
    `message` TEXT NOT NULL,
    `action_command` VARCHAR(255) DEFAULT NULL COMMENT 'bounded catalog only, e.g. EMOTE 1 or PORTAL ORGRIMMAR',
    `status` TINYINT NOT NULL DEFAULT 0 COMMENT '0=Pending, 1=Delivered, 2=Failed',
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
    `memory_type` VARCHAR(32) NOT NULL DEFAULT 'CONVERSATION' COMMENT 'CONVERSATION, BOSS_KILL, WIPE, TRADE, QUEST',
    `memory_text` TEXT NOT NULL,
    `importance_score` TINYINT UNSIGNED NOT NULL DEFAULT 5 COMMENT '1 (trivial) to 10 (epic)',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    INDEX `idx_player_bot` (`player_name`, `bot_name`),
    INDEX `idx_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO `synthetic_bot_personas` (`bot_name`, `class_name`, `race_name`, `personality_traits`, `speech_style`, `backstory`) VALUES
('Brog', 'Warrior', 'Orc', 'Steadfast, protective, and genuinely fond of his adventuring companions', 'Warm but gruff, with dry situational humor and no party-member insults', 'Veteran of the Third War who prefers heavy plate and giant two-handed axes.'),
('Lyra', 'Mage', 'Blood Elf', 'Clever, curious, loyal, and enthusiastic about solving problems', 'Witty, articulate, warm, and helpful without jokes at a party member expense', 'Former Silvermoon scholar who studies ancient arcane anomalies in Northrend.'),
('Theron', 'Paladin', 'Human', 'Selfless, patient, protective, and attentive to party needs', 'Encouraging and warm without preaching or lecturing', 'Knight of the Silver Hand dedicated to defending traveling adventurers from undead scourge.'),
('Fizwick', 'Rogue', 'Gnome', 'Inventive, cheerful, and eager to help friends with gadgets and locks', 'Energetic and playful without repetitive needling', 'Tinkerer-turned-scoundrel who claims he only picks pockets to test spring tensions.'),
('Eluneis', 'Druid', 'Night Elf', 'Calm, patient, deeply connected to nature and shapeshifting forms', 'Poetic, gentle, speaks with nature metaphors and quiet wisdom', 'Cenarion Circle guardian tasked with restoring corrupted wildlife in Azeroth.');
