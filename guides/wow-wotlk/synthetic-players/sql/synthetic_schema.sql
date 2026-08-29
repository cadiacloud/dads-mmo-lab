-- ============================================================================
-- Dad's MMO Lab: Synthetic Players Database Schema
-- Expansion: Wrath of the Lich King (3.3.5a) / AzerothCore
-- Schema Target: acore_characters
-- ============================================================================

-- 1. Inbox: Game events & player chat sent from Eluna to Python Agent Daemon
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

-- 2. Outbox: LLM-generated dialogue and tactical actions to be executed in-game by Eluna
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

-- 3. Bot Personas: Personality archetypes, speech quirks, and background lore
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

-- 4. Action audit: distinguishes chat delivery from accepted/rejected actions
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

-- 5. Canonical persona-to-Playerbot bindings, including reversible original names
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

-- Explicit, auditable in-game Cadia authority. Empty by default.
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

-- Candidate plans cannot change a character until separately approved.
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

-- Farming/crafting/trading/AH work is proposed here before bounded execution.
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

-- Runtime economy policy for real character-owned market participation.
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

INSERT IGNORE INTO `synthetic_economy_profiles` (`bot_guid`, `bot_name`)
SELECT `character_guid`, `persona_name`
FROM `synthetic_persona_bindings`
WHERE LOWER(`persona_name`) IN ('lyra', 'celene', 'ray', 'browntown');

-- 6. Typed high-level intents awaiting the trusted Playerbots executor
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
    `status` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '0=pending, 1=accepted, 2=running, 3=succeeded, 4=failed, 5=rejected, 6=expired, 7=preempted',
    `reported_status` TINYINT UNSIGNED DEFAULT NULL,
    `result_code` VARCHAR(64) NOT NULL DEFAULT '',
    PRIMARY KEY (`id`),
    INDEX `idx_synthetic_intent_pending` (`status`, `expires_at`, `id`),
    INDEX `idx_synthetic_intent_reporting` (`reported_status`, `status`, `id`),
    INDEX `idx_synthetic_intent_bot` (`bot_guid`, `created_at`),
    CONSTRAINT `fk_synthetic_intent_inbox` FOREIGN KEY (`inbox_id`) REFERENCES `synthetic_inbox` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. Append-only lifecycle evidence for each typed intent
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

-- 8. Bounded worldserver perception for persona reasoning and verification
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

-- 9. Authoritative in-memory bag/equipment projection for grounded replies
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

-- 10. Persistent Memories: Shared experiences and relationship tracking between players and bots
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

-- 10. Bounded LLM-authored gathering plans and deterministic execution ledger
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


-- Seed the explicitly allowlisted LLM-controlled personas. Other Playerbots remain native AI.
INSERT IGNORE INTO `synthetic_bot_personas` (`bot_name`, `class_name`, `race_name`, `personality_traits`, `speech_style`, `backstory`) VALUES
('Lyra', 'Mage', 'Blood Elf', 'Clever, curious, loyal, and enthusiastic about solving problems', 'Witty, articulate, warm, and helpful without jokes at a party member expense', 'Former Silvermoon scholar who studies ancient arcane anomalies in Northrend.'),
('Celene', 'Rogue', 'Blood Elf', 'Observant, disciplined, loyal to the group, and generous with useful finds', 'Concise, friendly, and calm without cruelty or condescension', 'Silvermoon field operative who puts reconnaissance, tradecraft, and precise control at the party service.'),
('Ray', 'Rogue', 'Orc', 'Loyal, perceptive, generous, and dependable as a scout', 'Friendly and practical; says Heh heh for deliberate jokes and occasionally in relaxed banter without spamming it', 'Young Durotar scout who earns every level beside trusted friends.'),
('Browntown', 'Mage', 'Orc', 'Bright, bold, curious, loyal, and generous with gathered materials', 'Warm, energetic, clever, and never condescending', 'Young Orc arcane talent who learns magic alongside trusted friends.');
