# Cadia WotLK Realm: 2026-08-30 Incremental Change Record

**Recorded:** 2026-08-30

**Game protocol:** World of Warcraft 3.3.5a, build 12340

**Scope:** the heroic-endpoint BOA rogue equipment package deployed after the
2026-08-29 realm record, its client/server compatibility boundary, and the GM
commands verified during the same operations session

This record extends, rather than replaces,
[`SERVER-CHANGES-2026-08-29.md`](./SERVER-CHANGES-2026-08-29.md). It deliberately
excludes account identities, character names and inventories, credentials,
addresses, machine-local paths, proprietary client data, and private chat.

## Outcome

The realm has an optional 17-item, rogue-only, bind-to-account set that scales
from level 1 through level 80 without modifying Blizzard's stock items. The two
Warglaives reproduce their original legendary damage and stats at level 70,
then continue to heroic ICC/RS-equivalent endpoints at level 80. The remaining
armor, jewelry, trinkets, cloak, and ranged weapon use Blizzard per-level curves
and documented heroic level-80 endpoints.

The portable implementation is in
[`boa-rogue-heirlooms/`](./boa-rogue-heirlooms/README.md) and consists of:

- additive `item_template` entries `900100` through `900116`;
- custom `ScalingStatDistribution.dbc` rows `9100` through `9116`;
- `mod-boa-rogue-heirlooms`, which supplies authoritative nonlinear Warglaive
  and weapon-damage scaling;
- a bounded AzerothCore hook adjustment that allows modules to refine items
  backed by a DBC scaling distribution;
- deterministic Item and ScalingStatDistribution DBC builders; and
- MPQ packaging support for installing both required DBC files in one client
  patch.

The module is independently disableable with:

```ini
BoaRogueHeirlooms.Enable = 0
```

Disabling it stops the custom authoritative curves but does not remove item
templates, persistent item instances, DBC rows, or the client patch.

## Power and item boundary

The package is intentionally stronger than a normal Blizzard heirloom at its
level-80 endpoint. Exact item names, source appearances, endpoint references,
socket plan, enchants, and scaling math are recorded in the package README.

At level 70:

- main-hand Warglaive damage is `214-398` at 2.8 speed;
- off-hand Warglaive damage is `107-199` at 1.4 speed; and
- both weapons are 109.3 DPS, matching the original legendaries.

At level 80:

- main-hand Warglaive damage is `518-964` at 2.8 speed;
- off-hand Warglaive damage is `245-456` at 1.4 speed; and
- the complete set lands on the documented heroic ICC/RS-equivalent stat
  budgets, with 1,399 passive armor penetration after the reference socket
  plan.

The server's equipped values are authoritative. The 3.3.5a client cannot
express the item-specific nonlinear level-70-to-80 Warglaive curve in its
tooltip and therefore displays the static level-80 damage endpoint.

## Required client compatibility patch

Every connecting client must receive the matching custom `Item.dbc` and
`ScalingStatDistribution.dbc` in an MPQ patch. A client without both DBC files
can reject equipment types, omit custom stats, or show invalid tooltips.

The repository contains builders and packaging source only. Proprietary DBC
and MPQ outputs remain untracked and must not be committed. Close the game
before replacing its patch, clear `Cache/WDB/enUS/itemcache.wdb`, and relaunch.

## Verified GM mount and riding commands

The Spectral Tiger item-to-spell mappings below were checked against the
deployed world templates; the riding ranks are the WotLK 3.3.5a trainer spell
and skill IDs. GM commands operate on the selected player, so select yourself
or clear any other player target before applying them to your own character.

Grant the learnable Swift Spectral Tiger reins:

```text
.additem 49284 1
```

The player then right-clicks the item. The direct spell alternative is:

```text
.learn 42777
```

The slower version uses item `49283` and spell `42776`.

Grant all WotLK riding ranks, Cold Weather Flying, and the complete riding
skill line:

```text
.learn 33388
.learn 33391
.learn 34090
.learn 34091
.learn 54197
.setskill 762 300 300
```

Riding capability and mount ownership are separate; these riding commands do
not grant every mount.

## Validation evidence

The following non-secret checks were completed on 2026-08-30:

- worldserver, authentication server, and database services were running;
- the worldserver startup log reported BOA heroic-endpoint scaling enabled;
- all 17 custom item templates existed with the expected distribution IDs;
- the deployed module source matched the portable source recorded here;
- the required client MPQ was present outside Git; and
- the Spectral Tiger item-to-spell mappings were confirmed from the deployed
  `item_template` records.

Repository validation also covers shell and Python syntax, deterministic DBC
builder behavior, patch applicability, SQL template boundaries, and whitespace
checks. Exact validation commands and results belong in the commit record
rather than generated binaries or private operational state.

## Risk and reversibility

Keep predeployment world-database, server DBC, and client-patch backups. To
roll back safely:

1. disable the module and rebuild/restart the worldserver;
2. restore the previous server DBC and client MPQ;
3. locate and remove every persistent instance of entries `900100-900116`
   from inventories, mail, auctions, guild banks, and other containers; and
4. only after verifying no instances remain, remove the custom templates and
   DBC rows.

Never delete custom templates while persistent instances still reference
them. That can leave orphaned or invalid character data.

## Authorization and provenance

Implementation of the BOA clone/scaling feature and the subsequent
documentation, commit, and push were explicitly authorized by the owner in the
authenticated working conversation. Decision authority belongs to the owner;
OpenAI Codex is the implementation and recording agent. This record was made
after the live deployment checks above and does not broaden authority to
publish credentials, private account or character state, network configuration,
or proprietary game data.
