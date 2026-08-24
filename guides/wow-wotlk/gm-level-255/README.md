# Level-255 GM equipment

Wrath of the Lich King is itemized for level 80. AzerothCore permits a GM
character to reach level 255, but it clamps combat-rating calculations to the
level-100 DBC rows and does not provide a native level-255 gear tier.

`sql/confluent_vanguard_paladin.sql` adds a deliberately overpowered,
paladin-only private-server set for GM and systems testing:

- eight plate pieces;
- a two-handed damage weapon;
- a one-handed weapon and shield alternative;
- custom item-set ID `9900`;
- custom item entries `900001` through `900011`.

The names are generic and contain no player-specific data. The set is not
campaign-balanced and must not be given to ordinary progression characters.

## Installation

Back up `acore_world`, import the SQL, and restart the worldserver so its in-memory
item template store sees the new entries. Install
`../ALE-Kegs/ConfluentVanguard/ConfluentVanguard.lua` in ALE's `lua_scripts`
directory as well. Then, in game:

```text
/target <your-character>
.additem set 9900
.maxskill
.save
```

Equip either the two-handed weapon or the one-hand/shield pair. If a client has
cached an older version of a custom item, exit the client and remove its
`Cache/WDB/enUS/itemcache.wdb` before reconnecting.

The script treats the eight armor pieces plus the one-hand sword and shield as
the complete tank set. It applies +100% Strength, Agility, Stamina, Intellect,
and Spirit through passive per-stat aura stacks. This deliberately avoids the
ordinary Elune's Blessing aura, which conflicts with Blessing of Kings and can
make current health appear to fall when a paladin refreshes the party buff. The
script preserves the character's health and power percentages whenever the set
bonus is added or removed.

The SQL `ItemSet` value is descriptive metadata for `.additem set 9900`; the
ALE entry-based check is authoritative for the multiplicative bonus. A stock
client lacks a custom `ItemSet.dbc` row and may log an item-set warning without
preventing the entry-based bonus.

## Required client item patch

The 3.3.5a client also uses `DBFilesClient/Item.dbc` for local equipment-class
checks. Without custom DBC rows, the server can equip the Confluent weapons but
the client reports errors such as `Must have a shield equipped` for Avenger's
Shield and rejects Hammer of the Righteous.

`tools/build_confluent_item_dbc.py` adds entries `900001` through `900011` to a
stock 3.3.5a `Item.dbc`. Package that result as `DBFilesClient\\Item.dbc` in a
version-1 MPQ named `Data/patch-4.MPQ`. `tools/mpq_pack.cpp` is a minimal
[StormLib](https://github.com/ladislav-zezula/StormLib) packer for that step.
The client must be fully closed while installing or replacing the MPQ, then
restarted. The server does not need to restart.

One reproducible build sequence is:

```bash
python tools/build_confluent_item_dbc.py \
  /path/to/stock/Item.dbc /tmp/confluent-dbc/DBFilesClient/Item.dbc

c++ -std=c++17 -O2 tools/mpq_pack.cpp -lstorm -o /tmp/mpq_pack
/tmp/mpq_pack /path/to/client/Data/patch-4.MPQ \
  /tmp/confluent-dbc/DBFilesClient/Item.dbc
```

Verify the MPQ contains exactly `DBFilesClient\\Item.dbc`, close every client
process before replacement, clear `itemcache.wdb`, and relaunch. Never commit
the proprietary source DBC or built MPQ to this repository.

## Reversibility

Do not delete a custom item template while an instance of that item still
exists in a character inventory, mail, auction, guild bank, or other persistent
container. Remove every `900001`-`900011` instance first, verify their absence,
then delete the bounded template range. Retaining unused templates is safer than
creating orphaned item instances.
