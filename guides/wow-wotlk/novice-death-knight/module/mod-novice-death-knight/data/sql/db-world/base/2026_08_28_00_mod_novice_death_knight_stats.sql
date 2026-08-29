DELETE FROM `player_class_stats` WHERE `Class` = 6 AND `Level` BETWEEN 1 AND 54;
INSERT INTO `player_class_stats`
    (`Class`, `Level`, `BaseHP`, `BaseMana`, `Strength`, `Agility`, `Stamina`, `Intellect`, `Spirit`)
SELECT 6, `Level`, `BaseHP`, 0, `Strength`, `Agility`, `Stamina`, `Intellect`, `Spirit`
FROM `player_class_stats`
WHERE `Class` = 1 AND `Level` BETWEEN 1 AND 54;
