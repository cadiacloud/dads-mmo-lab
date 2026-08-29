# Novice Death Knight

`mod-novice-death-knight` provides an opt-in, server-side level 1 Death Knight
progression for AzerothCore WotLK. The module is disabled by default and does
not change `StartHeroicPlayerLevel`.

When enabled, only Death Knights created while the module is active are
enrolled. Existing Death Knights and Playerbots created through internal
sessions are not changed. Enrolled characters receive:

- level 1-54 base health and attributes derived from AzerothCore's Warrior
  curve, which joins the stock Death Knight curve at level 55;
- a racial starting location instead of the Ebon Hold introduction;
- level 1 mail equipment, a two-handed sword, and a hearthstone;
- normal talent progression beginning at level 10, including while visiting
  Ebon Hold;
- a staged Death Knight ability progression through level 80; and
- server-side scaling for non-weapon Death Knight spell damage below level 55.

The stock WotLK client has no low-level Death Knight spell ranks. The module
therefore scales server-authoritative damage while leaving the original client
tooltips unchanged below level 55.

## Ability progression

| Level | Abilities |
| ---: | --- |
| 1 | Icy Touch, Plague Strike |
| 2 | Blood Strike |
| 4 | Death Coil |
| 6 | Death Grip |
| 8 | Blood Presence |
| 10 | Dark Command |
| 12 | Pestilence |
| 14 | Mind Freeze |
| 16 | Chains of Ice |
| 18 | Death Strike |
| 20 | Frost Presence |
| 22 | Raise Dead |
| 24 | Blood Boil |
| 26 | Strangulate |
| 28 | Death and Decay |
| 30 | Path of Frost |
| 32 | Icebound Fortitude |
| 34 | Obliterate |
| 36 | Blood Tap |
| 38 | Horn of Winter |
| 40 | Death Pact |
| 42 | Rune Strike |
| 44 | Anti-Magic Shell |
| 46 | Unholy Presence |
| 48 | Raise Ally |
| 50 | Empower Rune Weapon |
| 54 | Army of the Dead |
| 55 | Death Gate, Runeforging, Acherus Deathcharger |

Normal trained ranks are learned automatically at their stock levels from
59-80. Talent-granted abilities remain controlled by the normal talent trees.

## Install

```bash
./install-novice-death-knight.sh \
  --server-root /absolute/path/to/azerothcore
```

Reconfigure and rebuild the worldserver so AzerothCore discovers the module.
The module's world and characters SQL files are then applied by AzerothCore's
normal database updater during startup.

This repository's Docker deployment uses the separate `ac-db-import` service
for core and module migrations. After installing or updating the module, run:

```bash
cd /absolute/path/to/azerothcore
docker compose build ac-worldserver ac-db-import
docker compose run --rm --no-deps ac-db-import
docker compose up -d --no-deps --force-recreate ac-worldserver
```

Run the database importer before the final worldserver recreation so the
level 1-54 class-stat curve is loaded during world initialization.

## Enable or disable

The installed module configuration is
`etc/modules/mod_novice_death_knight.conf`:

```ini
NoviceDeathKnight.Enable = 1
```

Set it to `0` and reload configuration or restart the worldserver to stop new
enrollment and all module behavior. Disabling does not delete enrolled
characters or their audit rows. The level 1-54 stat rows remain in the world
database as inert compatibility data and do not affect stock level-55 Death
Knights.

For the repository's Docker deployment, use the same master switch in
`env/dist/etc/modules/mod_novice_death_knight.conf`:

```ini
NoviceDeathKnight.Enable = 1
```

Change it to `0` and recreate only `ac-worldserver` to disable the feature.

## Boundaries

- The Ebon Hold starter quest line is skipped; racial-zone quests provide the
  leveling path.
- Class-specific racial trainer quests may not recognize Death Knights. Core
  combat abilities are learned automatically by this module.
- The module does not enroll Playerbots created with an empty/internal world
  session unless `NoviceDeathKnight.AllowInternalSessions` is explicitly set.
- A character enrolled while enabled remains marked if the module is later
  disabled. Re-enable the module to resume its progression behavior.
