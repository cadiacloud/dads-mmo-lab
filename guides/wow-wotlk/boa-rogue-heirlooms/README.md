# Heroic-endpoint BOA rogue set

This optional package adds a complete rogue-only, account-bound set that
scales from level 1 through level 80. It preserves the requested Warglaive and
Terrorblade appearances without changing any stock Blizzard item.

The package has two explicit power breakpoints:

- At level 70, the main- and off-hand Warglaives have the original level-70
  legendary stats, speed, damage, and DPS.
- At level 80, every slot reaches the stat budget of the selected heroic
  25-player ICC/RS or equivalent endgame item. The Warglaives reach normalized
  heroic one-hand damage while retaining their original 2.8/1.4 speeds.

This is intentionally stronger than a normal Blizzard heirloom at level 80.
The server module, not the client tooltip, is authoritative while leveling.

## Contents and level-80 endpoints

| Entry | Appearance | Level-80 power endpoint |
|---:|---|---|
| 900100 | Warglaive, main hand | Havoc's Call (50737), normalized to 2.8 speed |
| 900101 | Warglaive, off hand | Scourgeborne Waraxe (50654), normalized to 1.4 speed |
| 900102 | Terrorblade chest | Ikfirus's Sack of Wonder (50656) |
| 900103 | Terrorblade hands | Aldriana's Gloves of Secrecy (50675) |
| 900104 | Terrorblade head | Sanctified Shadowblade Helmet (51252) |
| 900105 | Terrorblade legs | Gangrenous Leggings (50697) |
| 900106 | Terrorblade shoulders | Sanctified Shadowblade Pauldrons (51254) |
| 900107 | Umbrage wrists | Toskk's Maximized Wristguards (50670) |
| 900108 | Astrylian waist | Heroic Astrylian's Sutured Cinch (50707) |
| 900109 | Frostbitten feet | Heroic Frostbitten Fur Boots (50607) |
| 900110 | Sindragosa neck | Heroic Sindragosa's Cruel Claw (50633) |
| 900111 | Shadowvault cloak | Vereesa's Dexterity (47545) |
| 900112 | Signet ring | Heroic Signet of Twilight (54576) |
| 900113 | Frostbrood ring | Ashen Band of Endless Vengeance (50402), including proc |
| 900114 | Twilight Scale | Heroic Sharpened Twilight Scale (54590), including proc |
| 900115 | Deathbringer's Will | Heroic Deathbringer's Will (50363), including proc |
| 900116 | Fal'inrush ranged | Heroic Fal'inrush (50733) |

The endpoint selection follows the Phase 5 Combat Rogue slot priorities in
the [Icy Veins Combat Rogue BiS guide](https://www.icy-veins.com/wotlk-classic/combat-rogue-dps-pve-gear-best-in-slot).
The appearances remain those named in the custom item column; only their
server-authoritative power budgets use the endpoint column.

## Exact scaling behavior

`mod-boa-rogue-heirlooms` implements the nonlinear parts that a stock WotLK
heirloom table cannot represent:

- Warglaive stats and damage follow the stock one-hand curve through level 70.
- At exactly 70, main hand is 214-398 at 2.8 speed and off hand is 107-199 at
  1.4 speed: 109.3 DPS each, matching the original legendaries.
- Levels 71-80 interpolate into 518-964 main-hand damage and 245-456 off-hand
  damage. Those endpoints are the heroic Havoc's Call and Scourgeborne Waraxe
  damage ranges normalized to the Warglaives' original speeds.
- Other item stats use Blizzard's normal per-level multipliers and land on the
  documented endpoint values at 80.
- Ranged damage uses Blizzard's ranged curve and lands on heroic Fal'inrush at
  80.
- Level 80 remains the ceiling.

The Warglaive client tooltip always displays the level-80 static damage range
because the 3.3.5a client has no item-specific nonlinear DPS curve. Equipped
damage is replaced by the server module at every level and is authoritative.
Custom stat tooltips reach the exact endpoint at 80; during leveling, the
character sheet and server combat values are authoritative.

The custom `ScalingStatDistribution.dbc` rows are 9100-9116. A bounded core
patch moves AzerothCore's existing custom-scaling hook so modules can refine
items that use a DBC distribution. The patch changes no stats by itself and
has no effect unless a module implements the hook.

## Min/max socket and enchant profile

The reference deployment uses the Combat Rogue endgame recommendations from
the [Icy Veins enchant and gem guide](https://www.icy-veins.com/wotlk-classic/combat-rogue-dps-pve-enchants-consumables)
and caps armor penetration according to the [WotLK Combat Rogue stat-priority
guide](https://www.wowhead.com/wotlk/guide/classes/rogue/combat/dps-stat-priority-attributes-pve).

At level 80 the package has 965 passive armor penetration. Its 24 sockets are:

- 20 Fractured Cardinal Rubies: 400 armor penetration
- 1 Fractured Dragon's Eye: 34 armor penetration
- 1 Delicate Cardinal Ruby: 20 agility
- 1 Relentless Earthsiege Diamond: 21 agility and 3% critical damage
- 1 Nightmare Tear: 10 all stats and all three colors for the meta condition

The result is exactly 1,399 armor penetration before temporary effects. The
loadout deliberately ignores lower-value socket bonuses where necessary to
reach the hard cap.

Permanent enchants are:

| Slot | Enchant |
|---|---|
| Head | Arcanum of Torment |
| Shoulders | Greater Inscription of the Axe |
| Back | Major Agility |
| Chest | Powerful Stats |
| Wrists | Greater Assault |
| Hands | Crusher |
| Legs | Icescale Leg Armor |
| Feet | Icewalker |
| Both rings | Assault |
| Both Warglaives | Berserking |
| Ranged | Sun Scope |
| Waist | Eternal Belt Buckle plus third gem |

The enchants and gems are static WotLK effects. Consequently, a fully prepared
set is stronger than ordinary leveling gear even though the cloned item stats
and weapon damage scale with level.

## Server installation

1. Install the module and bounded core hook patch:

   ```bash
   ./install-boa-rogue-heirlooms.sh \
     --server-root /absolute/path/to/azerothcore
   ```

2. Patch the server's `ScalingStatDistribution.dbc` from its stock DBC:

   ```bash
   python tools/build_boa_rogue_scaling_dbc.py \
     /path/to/stock/ScalingStatDistribution.dbc \
     /path/to/server/data/dbc/ScalingStatDistribution.dbc
   ```

3. Back up `acore_world`, import `sql/boa_rogue_heirlooms.sql`, rebuild the
   worldserver, and restart it.

The module is enabled by default and can be disabled with:

```ini
BoaRogueHeirlooms.Enable = 0
```

Disabling the module leaves the custom items and their DBC endpoints installed,
but removes the exact nonlinear Warglaive and authoritative stat overrides.

## Required client patch

Every connecting client needs both matching DBC files. Without them, the
client can reject weapon types, omit custom stats, or show invalid tooltips.

Build from clean 3.3.5a DBC inputs. If the Confluent Vanguard GM items are also
installed, apply both Item builders in sequence:

```bash
python ../gm-level-255/tools/build_confluent_item_dbc.py \
  /path/to/stock/Item.dbc /tmp/combined/Item.gm.dbc
python tools/build_boa_rogue_item_dbc.py \
  /tmp/combined/Item.gm.dbc /tmp/combined/Item.dbc
python tools/build_boa_rogue_scaling_dbc.py \
  /path/to/stock/ScalingStatDistribution.dbc \
  /tmp/combined/ScalingStatDistribution.dbc

c++ -std=c++17 -O2 ../gm-level-255/tools/mpq_pack.cpp \
  -lstorm -o /tmp/mpq_pack
/tmp/mpq_pack /path/to/client/Data/patch-4.MPQ \
  /tmp/combined/Item.dbc \
  /tmp/combined/ScalingStatDistribution.dbc
```

Close the client before replacing the MPQ, move or delete
`Cache/WDB/enUS/itemcache.wdb`, and relaunch. Do not commit proprietary DBC or
MPQ outputs.

## Delivery

A WotLK mail supports at most 12 attachments, so an unprepared set requires two
messages:

```text
send items <character> "BOA rogue heirlooms 1/2" "Weapons, Terrorblade, and armor." 900100:1 900101:1 900102:1 900103:1 900104:1 900105:1 900106:1 900107:1 900108:1 900109:1 900110:1 900111:1
send items <character> "BOA rogue heirlooms 2/2" "Rings, trinkets, and ranged weapon." 900112:1 900113:1 900114:1 900115:1 900116:1
```

Direct database enchant/socket preparation must be performed only while the
character and worldserver are offline. Preserve the existing item GUIDs; do
not resend a second set merely to prepare it.

## Reversibility

Keep the predeployment world database, server DBC, and client MPQ backups.
Restore those files and rebuild without the module to roll back. Never delete a
custom template while an instance still exists in character inventory, mail,
auction, guild bank, or another persistent container. Remove all instances,
verify the range is unused, and only then remove entries 900100-900116 and DBC
rows 9100-9116.
