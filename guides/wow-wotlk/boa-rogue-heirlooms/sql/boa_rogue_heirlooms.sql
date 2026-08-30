-- BOA rogue heirlooms for AzerothCore WotLK 3.3.5a.
--
-- Additive custom range: item entries 900100-900116. The stock source items
-- are never changed. Entries 9100-9116 in ScalingStatDistribution.dbc and the
-- mod-boa-rogue-heirlooms server module are required. Together they provide a
-- level-70 Warglaive breakpoint and heroic ICC/RS level-80 endpoint.
-- A worldserver restart is required after import or module/DBC replacement.

DROP TEMPORARY TABLE IF EXISTS `_boa_rogue_item`;
CREATE TEMPORARY TABLE `_boa_rogue_item` LIKE `item_template`;

START TRANSACTION;

-- Re-importing replaces only this package's bounded template range. Do not
-- remove these templates while persistent item instances still reference them.
DELETE FROM `item_template` WHERE `entry` BETWEEN 900100 AND 900116;

INSERT INTO `_boa_rogue_item`
SELECT * FROM `item_template`
WHERE `entry` IN (
    32837, 32838,
    46123, 46124, 46125, 46126, 46127,
    54580, 50707, 50607,
    50633, 50653,
    54576, 50618,
    54590, 50363,
    50733
);

UPDATE `_boa_rogue_item`
SET
    `name` = CASE `entry`
        WHEN 32837 THEN 'Heirloom Warglaive of Azzinoth (Main Hand)'
        WHEN 32838 THEN 'Heirloom Warglaive of Azzinoth (Off Hand)'
        WHEN 46123 THEN 'Heirloom Terrorblade Breastplate'
        WHEN 46124 THEN 'Heirloom Terrorblade Gauntlets'
        WHEN 46125 THEN 'Heirloom Terrorblade Helmet'
        WHEN 46126 THEN 'Heirloom Terrorblade Legplates'
        WHEN 46127 THEN 'Heirloom Terrorblade Pauldrons'
        WHEN 54580 THEN 'Heirloom Umbrage Armbands'
        WHEN 50707 THEN 'Heirloom Astrylian\'s Sutured Cinch'
        WHEN 50607 THEN 'Heirloom Frostbitten Fur Boots'
        WHEN 50633 THEN 'Heirloom Sindragosa\'s Cruel Claw'
        WHEN 50653 THEN 'Heirloom Shadowvault Slayer\'s Cloak'
        WHEN 54576 THEN 'Heirloom Signet of Twilight'
        WHEN 50618 THEN 'Heirloom Frostbrood Sapphire Ring'
        WHEN 54590 THEN 'Heirloom Sharpened Twilight Scale'
        WHEN 50363 THEN 'Heirloom Deathbringer\'s Will'
        WHEN 50733 THEN 'Heirloom Fal\'inrush, Defender of Quel\'thalas'
    END,
    `Quality` = 7,
    -- ITEM_FLAG_IS_BOUND_TO_ACCOUNT | ITEM_FLAG_ITEM_PURCHASE_RECORD. This
    -- matches stock WotLK heirlooms and intentionally removes Heroic,
    -- Unique-Equipped, and other source-specific flags.
    `Flags` = 134221824,
    `FlagsExtra` = 0,
    `BuyCount` = 1,
    `BuyPrice` = 0,
    `SellPrice` = 0,
    `AllowableClass` = 8,
    `AllowableRace` = -1,
    `ItemLevel` = 284,
    `RequiredLevel` = 0,
    `RequiredSkill` = 0,
    `RequiredSkillRank` = 0,
    `requiredspell` = 0,
    `requiredhonorrank` = 0,
    `RequiredCityRank` = 0,
    `RequiredReputationFaction` = 0,
    `RequiredReputationRank` = 0,
    `maxcount` = 0,
    `stackable` = 1,
    `stat_type1` = 0, `stat_value1` = 0,
    `stat_type2` = 0, `stat_value2` = 0,
    `stat_type3` = 0, `stat_value3` = 0,
    `stat_type4` = 0, `stat_value4` = 0,
    `stat_type5` = 0, `stat_value5` = 0,
    `stat_type6` = 0, `stat_value6` = 0,
    `stat_type7` = 0, `stat_value7` = 0,
    `stat_type8` = 0, `stat_value8` = 0,
    `stat_type9` = 0, `stat_value9` = 0,
    `stat_type10` = 0, `stat_value10` = 0,
    `ScalingStatDistribution` = CASE `entry`
        WHEN 32837 THEN 9100 WHEN 32838 THEN 9101
        WHEN 46123 THEN 9102 WHEN 46124 THEN 9103
        WHEN 46125 THEN 9104 WHEN 46126 THEN 9105
        WHEN 46127 THEN 9106 WHEN 54580 THEN 9107
        WHEN 50707 THEN 9108 WHEN 50607 THEN 9109
        WHEN 50633 THEN 9110 WHEN 50653 THEN 9111
        WHEN 54576 THEN 9112 WHEN 50618 THEN 9113
        WHEN 54590 THEN 9114 WHEN 50363 THEN 9115
        WHEN 50733 THEN 9116
    END,
    `ScalingStatValue` = CASE
        -- Weapon stats scale through the custom distribution. Weapon damage is
        -- server-authoritative in the module, so the client receives the
        -- heroic endpoint as static damage rather than the stock 120-DPS cap.
        WHEN `entry` IN (32837, 32838) THEN 4
        -- Large leather pieces use the stock leather chest armor curve.
        WHEN `entry` IN (46123, 46125, 46126) THEN 2097160
        -- Smaller leather pieces use the stock leather shoulder armor curve.
        WHEN `entry` IN (46124, 46127, 54580, 50707, 50607) THEN 65
        -- Cloak uses the ring-sized stat curve plus the cloak armor curve.
        WHEN `entry` = 50653 THEN 786432
        -- Neck and rings use the ring-sized stat curve.
        WHEN `entry` IN (50633, 54576, 50618) THEN 262144
        -- Trinkets use the trinket stat curve.
        WHEN `entry` IN (54590, 50363) THEN 2
        -- Ranged stats scale through the custom distribution; ranged damage is
        -- server-authoritative in the module.
        WHEN `entry` = 50733 THEN 16
    END,
    -- Static client endpoints. The module replaces these values with the
    -- wearer's level-specific authoritative values when equipped.
    `dmg_min1` = CASE
        WHEN `entry` = 32837 THEN 518
        WHEN `entry` = 32838 THEN 245
        WHEN `entry` = 50733 THEN 783
        ELSE 0
    END,
    `dmg_max1` = CASE
        WHEN `entry` = 32837 THEN 964
        WHEN `entry` = 32838 THEN 456
        WHEN `entry` = 50733 THEN 1071
        ELSE 0
    END,
    `dmg_type1` = 0,
    `dmg_min2` = 0,
    `dmg_max2` = 0,
    `dmg_type2` = 0,
    `spellid_1` = CASE
        WHEN `entry` = 54590 THEN 75457
        WHEN `entry` = 50363 THEN 71562
        WHEN `entry` = 50618 THEN 71650
        ELSE 0
    END,
    `spelltrigger_1` = CASE
        WHEN `entry` IN (54590, 50363) THEN 1
        WHEN `entry` = 50618 THEN 5
        ELSE 0
    END,
    `spellcharges_1` = 0,
    `spellppmRate_1` = 0, `spellcooldown_1` = -1,
    `spellcategory_1` = 0, `spellcategorycooldown_1` = -1,
    `spellid_2` = CASE WHEN `entry` = 50618 THEN 72413 ELSE 0 END,
    `spelltrigger_2` = CASE WHEN `entry` = 50618 THEN 1 ELSE 0 END,
    `spellcharges_2` = 0,
    `spellppmRate_2` = 0, `spellcooldown_2` = -1,
    `spellcategory_2` = 0, `spellcategorycooldown_2` = -1,
    `spellid_3` = 0, `spelltrigger_3` = 0, `spellcharges_3` = 0,
    `spellppmRate_3` = 0, `spellcooldown_3` = -1,
    `spellcategory_3` = 0, `spellcategorycooldown_3` = -1,
    `spellid_4` = 0, `spelltrigger_4` = 0, `spellcharges_4` = 0,
    `spellppmRate_4` = 0, `spellcooldown_4` = -1,
    `spellcategory_4` = 0, `spellcategorycooldown_4` = -1,
    `spellid_5` = 0, `spelltrigger_5` = 0, `spellcharges_5` = 0,
    `spellppmRate_5` = 0, `spellcooldown_5` = -1,
    `spellcategory_5` = 0, `spellcategorycooldown_5` = -1,
    `bonding` = 1,
    `description` = 'Account-bound rogue heirloom. Server-scaled through level 80; heroic ICC/RS endpoint.',
    `PageText` = 0,
    `LanguageID` = 0,
    `PageMaterial` = 0,
    `startquest` = 0,
    `lockid` = 0,
    `RandomProperty` = 0,
    `RandomSuffix` = 0,
    `block` = 0,
    `itemset` = 0,
    `area` = 0,
    `Map` = 0,
    `socketColor_1` = CASE
        WHEN `entry` = 32837 THEN 2
        WHEN `entry` = 46125 THEN 1
        WHEN `entry` IN (32838, 46126, 54580, 54576, 50618) THEN 4
        WHEN `entry` = 46123 THEN 2
        WHEN `entry` = 46124 THEN 4
        WHEN `entry` = 46127 THEN 2
        WHEN `entry` = 50707 THEN 8
        WHEN `entry` = 50607 THEN 4
        WHEN `entry` = 50633 THEN 8
        WHEN `entry` = 50653 THEN 2
        WHEN `entry` = 50733 THEN 2
        ELSE 0
    END,
    `socketContent_1` = 0,
    `socketColor_2` = CASE
        WHEN `entry` IN (46124, 46125, 50707, 50607) THEN 2
        WHEN `entry` = 46123 THEN 8
        WHEN `entry` = 46126 THEN 2
        ELSE 0
    END,
    `socketContent_2` = 0,
    `socketColor_3` = CASE
        WHEN `entry` = 46123 THEN 4
        WHEN `entry` = 46126 THEN 8
        ELSE 0
    END,
    `socketContent_3` = 0,
    `socketBonus` = 0,
    `GemProperties` = 0,
    `RequiredDisenchantSkill` = -1,
    `ArmorDamageModifier` = 0,
    `duration` = 0,
    `ItemLimitCategory` = 0,
    `HolidayId` = 0,
    `ScriptName` = '',
    `DisenchantID` = 0,
    `FoodType` = 0,
    `minMoneyLoot` = 0,
    `maxMoneyLoot` = 0,
    `flagsCustom` = 0,
    `VerifiedBuild` = NULL,
    -- Keep this assignment last: MySQL evaluates single-table assignments
    -- from left to right, and every prior CASE is keyed by the stock entry.
    `entry` = CASE `entry`
        WHEN 32837 THEN 900100
        WHEN 32838 THEN 900101
        WHEN 46123 THEN 900102
        WHEN 46124 THEN 900103
        WHEN 46125 THEN 900104
        WHEN 46126 THEN 900105
        WHEN 46127 THEN 900106
        WHEN 54580 THEN 900107
        WHEN 50707 THEN 900108
        WHEN 50607 THEN 900109
        WHEN 50633 THEN 900110
        WHEN 50653 THEN 900111
        WHEN 54576 THEN 900112
        WHEN 50618 THEN 900113
        WHEN 54590 THEN 900114
        WHEN 50363 THEN 900115
        WHEN 50733 THEN 900116
    END;

INSERT INTO `item_template` SELECT * FROM `_boa_rogue_item`;

COMMIT;
DROP TEMPORARY TABLE `_boa_rogue_item`;

SELECT
    `entry`, `name`, `Quality`, `Flags`, `AllowableClass`, `ItemLevel`,
    `RequiredLevel`, `InventoryType`, `ScalingStatDistribution`,
    `ScalingStatValue`, `itemset`
FROM `item_template`
WHERE `entry` BETWEEN 900100 AND 900116
ORDER BY `entry`;
