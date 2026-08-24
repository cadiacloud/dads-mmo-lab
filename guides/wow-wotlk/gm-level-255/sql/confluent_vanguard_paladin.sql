-- Confluent Vanguard: level-255 paladin GM equipment for AzerothCore WotLK.
-- Additive custom range: item entries 900001-900011; item set 9900.
-- This content is deliberately overpowered and intended only for private-server
-- GM and systems testing. A worldserver restart is required after import.

DROP TEMPORARY TABLE IF EXISTS `_confluent_vanguard_item`;
CREATE TEMPORARY TABLE `_confluent_vanguard_item` LIKE `item_template`;

START TRANSACTION;

-- The range was selected outside the stock WotLK item namespace. Re-importing
-- replaces only this migration's bounded templates.
DELETE FROM `item_template` WHERE `entry` BETWEEN 900001 AND 900011;

-- Eight pieces of visually coherent ICC paladin plate.
INSERT INTO `_confluent_vanguard_item`
SELECT * FROM `item_template`
WHERE `entry` IN (51277, 51279, 51275, 51276, 51278, 50667, 54578, 50611);

UPDATE `_confluent_vanguard_item`
SET
    `name` = CASE `entry`
        WHEN 51277 THEN 'Confluent Vanguard Greathelm'
        WHEN 51279 THEN 'Confluent Vanguard Pauldrons'
        WHEN 51275 THEN 'Confluent Vanguard Battleplate'
        WHEN 51276 THEN 'Confluent Vanguard Gauntlets'
        WHEN 51278 THEN 'Confluent Vanguard Legplates'
        WHEN 50667 THEN 'Confluent Vanguard Girdle'
        WHEN 54578 THEN 'Confluent Vanguard Sabatons'
        WHEN 50611 THEN 'Confluent Vanguard Bracers'
    END,
    `Quality` = 5,
    `Flags` = 8,
    `FlagsExtra` = 0,
    `BuyPrice` = 0,
    `SellPrice` = 0,
    `AllowableClass` = 2,
    `AllowableRace` = -1,
    `ItemLevel` = 435,
    `RequiredLevel` = 255,
    `RequiredSkill` = 0,
    `RequiredSkillRank` = 0,
    `requiredspell` = 0,
    `RequiredReputationFaction` = 0,
    `RequiredReputationRank` = 0,
    `maxcount` = 0,
    `stackable` = 1,
    `stat_type1` = 4,
    `stat_value1` = 1500,
    `stat_type2` = 7,
    `stat_value2` = 2000,
    `stat_type3` = 5,
    `stat_value3` = 1000,
    `stat_type4` = 31,
    `stat_value4` = 400,
    `stat_type5` = 32,
    `stat_value5` = 500,
    `stat_type6` = 36,
    `stat_value6` = 500,
    `stat_type7` = 37,
    `stat_value7` = 350,
    `stat_type8` = 38,
    `stat_value8` = 800,
    `stat_type9` = 45,
    `stat_value9` = 800,
    `stat_type10` = 12,
    `stat_value10` = 350,
    `ScalingStatDistribution` = 0,
    `ScalingStatValue` = 0,
    `armor` = CASE `entry`
        WHEN 51275 THEN 18000
        WHEN 51278 THEN 16000
        WHEN 51277 THEN 15000
        WHEN 51279 THEN 12000
        WHEN 51276 THEN 10000
        ELSE 8000
    END,
    `bonding` = 1,
    `description` = 'Level-255 private-server GM equipment. Not campaign-balanced.',
    `RandomProperty` = 0,
    `RandomSuffix` = 0,
    `itemset` = 9900,
    `socketColor_1` = 2,
    `socketContent_1` = 0,
    `socketColor_2` = 4,
    `socketContent_2` = 0,
    `socketColor_3` = 8,
    `socketContent_3` = 0,
    `socketBonus` = 0,
    `GemProperties` = 0,
    `RequiredDisenchantSkill` = -1,
    `DisenchantID` = 0,
    `flagsCustom` = 0,
    `VerifiedBuild` = NULL,
    `entry` = CASE `entry`
        WHEN 51277 THEN 900001
        WHEN 51279 THEN 900002
        WHEN 51275 THEN 900003
        WHEN 51276 THEN 900004
        WHEN 51278 THEN 900005
        WHEN 50667 THEN 900006
        WHEN 54578 THEN 900007
        WHEN 50611 THEN 900008
    END;

INSERT INTO `item_template` SELECT * FROM `_confluent_vanguard_item`;
DELETE FROM `_confluent_vanguard_item`;

-- Two-handed, one-handed, and shield choices. All three are included in set
-- 9900 so the GM can change role without another database operation.
INSERT INTO `_confluent_vanguard_item`
SELECT * FROM `item_template` WHERE `entry` IN (50730, 51869, 50729);

UPDATE `_confluent_vanguard_item`
SET
    `name` = CASE `entry`
        WHEN 50730 THEN 'Confluent Judgment'
        WHEN 51869 THEN 'Confluent Oathblade'
        WHEN 50729 THEN 'Confluent Bulwark'
    END,
    `Quality` = 5,
    `Flags` = 8,
    `FlagsExtra` = 0,
    `BuyPrice` = 0,
    `SellPrice` = 0,
    `AllowableClass` = 2,
    `AllowableRace` = -1,
    `ItemLevel` = 435,
    `RequiredLevel` = 255,
    `RequiredSkill` = 0,
    `RequiredSkillRank` = 0,
    `requiredspell` = 0,
    `RequiredReputationFaction` = 0,
    `RequiredReputationRank` = 0,
    `maxcount` = 0,
    `stackable` = 1,
    `stat_type1` = 4,
    `stat_value1` = CASE `entry` WHEN 50730 THEN 3000 WHEN 51869 THEN 2200 ELSE 2000 END,
    `stat_type2` = 7,
    `stat_value2` = CASE `entry` WHEN 50730 THEN 4000 WHEN 51869 THEN 3000 ELSE 5000 END,
    `stat_type3` = 5,
    `stat_value3` = CASE `entry` WHEN 50730 THEN 2000 WHEN 51869 THEN 2200 ELSE 2000 END,
    `stat_type4` = 31,
    `stat_value4` = CASE `entry` WHEN 50729 THEN 750 ELSE 1000 END,
    `stat_type5` = 32,
    `stat_value5` = CASE `entry` WHEN 50729 THEN 750 ELSE 1000 END,
    `stat_type6` = 36,
    `stat_value6` = CASE `entry` WHEN 50729 THEN 750 ELSE 1000 END,
    `stat_type7` = 37,
    `stat_value7` = CASE `entry` WHEN 50729 THEN 1000 ELSE 800 END,
    `stat_type8` = 38,
    `stat_value8` = CASE `entry` WHEN 50730 THEN 3000 WHEN 51869 THEN 2200 ELSE 1500 END,
    `stat_type9` = 45,
    `stat_value9` = CASE `entry` WHEN 50730 THEN 3000 WHEN 51869 THEN 3000 ELSE 2000 END,
    `stat_type10` = 12,
    `stat_value10` = CASE `entry` WHEN 50729 THEN 2500 ELSE 800 END,
    `ScalingStatDistribution` = 0,
    `ScalingStatValue` = 0,
    `dmg_min1` = CASE `entry` WHEN 50730 THEN 15000 WHEN 51869 THEN 7500 ELSE 0 END,
    `dmg_max1` = CASE `entry` WHEN 50730 THEN 22000 WHEN 51869 THEN 10500 ELSE 0 END,
    `dmg_type1` = 0,
    `dmg_min2` = 0,
    `dmg_max2` = 0,
    `dmg_type2` = 0,
    `armor` = CASE `entry` WHEN 50729 THEN 30000 ELSE 0 END,
    `block` = CASE `entry` WHEN 50729 THEN 6000 ELSE 0 END,
    `delay` = CASE `entry` WHEN 50730 THEN 3600 WHEN 51869 THEN 1800 ELSE 0 END,
    `bonding` = 1,
    `description` = 'Level-255 private-server GM equipment. Not campaign-balanced.',
    `RandomProperty` = 0,
    `RandomSuffix` = 0,
    `itemset` = 9900,
    `socketColor_1` = 2,
    `socketContent_1` = 0,
    `socketColor_2` = 4,
    `socketContent_2` = 0,
    `socketColor_3` = 8,
    `socketContent_3` = 0,
    `socketBonus` = 0,
    `GemProperties` = 0,
    `RequiredDisenchantSkill` = -1,
    `DisenchantID` = 0,
    `flagsCustom` = 0,
    `VerifiedBuild` = NULL,
    `entry` = CASE `entry`
        WHEN 50730 THEN 900009
        WHEN 51869 THEN 900010
        WHEN 50729 THEN 900011
    END;

INSERT INTO `item_template` SELECT * FROM `_confluent_vanguard_item`;

COMMIT;
DROP TEMPORARY TABLE `_confluent_vanguard_item`;

SELECT `entry`, `name`, `ItemLevel`, `RequiredLevel`, `InventoryType`, `itemset`
FROM `item_template`
WHERE `entry` BETWEEN 900001 AND 900011
ORDER BY `entry`;
