CREATE TABLE IF NOT EXISTS `novice_death_knight_characters` (
    `character_guid` INT UNSIGNED NOT NULL,
    `initialized` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `active` TINYINT UNSIGNED NOT NULL DEFAULT 1,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`character_guid`),
    CONSTRAINT `fk_novice_death_knight_character`
        FOREIGN KEY (`character_guid`) REFERENCES `characters` (`guid`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
