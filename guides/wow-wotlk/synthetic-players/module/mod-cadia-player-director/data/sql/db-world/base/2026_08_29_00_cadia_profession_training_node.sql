-- Stable, non-pooled Copper Vein used to bootstrap and acceptance-test the
-- controlled profession director at Mining skill 1. It uses the normal WotLK
-- Copper Vein template, gathering spell, loot table, skill-up rules, and
-- respawn handling; no items or skill points are granted by this migration.

SET @CADIA_COPPER_GUID := (SELECT COALESCE(MAX(`guid`), 0) + 1 FROM `gameobject`);

INSERT INTO `gameobject`
    (`guid`, `id`, `map`, `zoneId`, `areaId`, `spawnMask`, `phaseMask`,
     `position_x`, `position_y`, `position_z`, `orientation`,
     `rotation0`, `rotation1`, `rotation2`, `rotation3`, `spawntimesecs`,
     `animprogress`, `state`, `ScriptName`, `VerifiedBuild`, `Comment`)
SELECT
    @CADIA_COPPER_GUID, `id`, `map`, 14, `areaId`, `spawnMask`, `phaseMask`,
    1511.0, -4688.0, 9.1, `orientation`,
    `rotation0`, `rotation1`, `rotation2`, `rotation3`, 30,
    `animprogress`, `state`, `ScriptName`, `VerifiedBuild`,
    'Cadia profession training Copper Vein'
FROM `gameobject`
WHERE `id` = 1731
  AND `zoneId` = 14
  AND NOT EXISTS (
      SELECT 1 FROM `gameobject`
      WHERE `Comment` = 'Cadia profession training Copper Vein'
  )
ORDER BY `guid`
LIMIT 1;
