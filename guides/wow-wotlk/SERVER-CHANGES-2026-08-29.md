# Cadia WotLK Realm: Deployment and Change Record

**Recorded:** 2026-08-29

**Game protocol:** World of Warcraft 3.3.5a, build 12340

**Scope:** the current Cadia private-realm implementation and its portable
source in this repository

This is a dated implementation and operations record, not a claim that every
setting is appropriate for every Dad's MMO Lab deployment. Runtime facts were
verified against the live deployment on the recording date. Host paths,
credentials, account names, public addresses, private chat, and other
machine-local data are deliberately omitted.

Individual account records, passwords, character inventories, appearance
overrides, current locations, guild rosters, and one-off GM grants are mutable
database state rather than portable server configuration. They belong in
access-controlled database backups and audit records, not in this public source
repository.

## Outcome

The realm now combines AzerothCore, Playerbots, quality-of-life modules, a
bounded local-LLM persona layer, and a compiled player-director executor. The
model directs high-level goals at decision boundaries; it does not attempt
frame-by-frame play and cannot submit arbitrary server, shell, SQL, GM, spell,
or Playerbots commands.

The implemented control path is:

```text
player chat or game event
  -> ALE SyntheticPlayers bridge
  -> database inbox
  -> event-driven local-LLM daemon or deterministic command router
  -> finite typed intent
  -> compiled Cadia Player Director authorization and execution
  -> Playerbots movement/combat/economy primitives
  -> observed terminal result
  -> deterministic in-game result message
```

There is no LLM heartbeat while the realm is idle. Model calls occur for chat,
eligible events, and explicit planning operations. Deterministic worldserver
code continues active plans without spending model tokens.

## Effective deployed stack

The following table separates portable defaults from effective live state. A
module being present does not mean its repository defaults are enabled.

| Component | Recorded revision or source | Effective state on 2026-08-29 |
| --- | --- | --- |
| AzerothCore Playerbots core | `9fb906bb7296212ff42fc95ff73a92aaf8554f0d` | auth, world, and database containers running |
| `mod-playerbots` | `5397110cba484a9b7209bc9f632652e9d4bd6a70` plus the level-255 patch below | 500 random bots requested and 500 reported online |
| `mod-ah-bot-plus` | `f685832994c825f90aa5a3dc0e1620aa568e875b` | seller and buyer enabled; 150 sell items per cycle |
| `mod-ale` | `c08b1a5e9118178c208513e7c789b1459c473a88` | enabled; runs the Synthetic Players bridge |
| `mod-arac` | `3f605e09c656eb3b620ef2d70c7ef61808c1cfb0` | installed for all-race/all-class support; compatible client patch required |
| `mod-learn-spells` | `016b92d520f343d074ffd5d46016a94f4a3a6ebd` | enabled through level 80; first-login mass learning disabled |
| `mod-quest-loot-party` | `6f073c1bef1bba1aa73787d1e30db7429f2b1c7b` | shared party quest loot enabled; extra module messages disabled |
| `mod-novice-death-knight` | source in this repository | enabled live; packaged default remains disabled; internal-session enrollment disabled |
| `mod-cadia-player-director` | source in this repository | enabled and executing typed intents/material objectives |
| Synthetic Players daemon | version `0.2.0`, source in this repository | running against a loopback OpenAI-compatible endpoint |
| Persona inference | local `cadia_persona` model alias | endpoint healthy on the recording date |

The live `mod-learn-spells` checkout also contains a const-spelling and
whitespace-only source delta. It does not alter behavior and is not promoted as
a required patch.

## Realm and Playerbots settings

The effective deployment settings are:

| Setting | Value | Effect |
| --- | ---: | --- |
| `AiPlayerbot.MinRandomBots` | 500 | requested autonomous population floor |
| `AiPlayerbot.MaxRandomBots` | 500 | requested autonomous population ceiling |
| `AiPlayerbot.SummonWhenGroup` | 0 | inviting a bot does not teleport it to the player |
| `AllowTwoSide.Interaction.Group` | 1 | Horde and Alliance may group together |
| `AllowTwoSide.Interaction.Auction` | 1 | both factions share auction interaction |
| `QuestParty.Enable` | 1 | eligible party members receive quest-item credit together |
| `QuestParty.Message` | 0 | suppresses additional quest-loot module chat |
| `ALE.Enabled` | 1 | activates the Lua event/action bridge |

The world and authentication ports are intentionally realm-facing. The
database and model endpoint remain loopback-scoped. Actual addresses, DNS,
firewall rules, and credentials are deployment secrets or variable operational
state and are not stored here.

## Level-255 Playerbots freeze fix

`RandomPlayerbotMgr::PrintStats()` used an 8-bit loop counter while
`maxBotLevel` could be 255. After reaching 255 the counter wrapped to zero, the
loop never terminated, and the world thread appeared frozen: creatures and
party bots stopped responding even though the process remained alive.

The portable patch widens only that iterator to `uint32`:

```bash
git -C /absolute/path/to/azerothcore/modules/mod-playerbots apply \
  /absolute/path/to/dads-mmo-lab/guides/wow-wotlk/patches/mod-playerbots-level-255-stats-loop.patch
```

Rebuild and recreate the worldserver after applying it. The patch is based on
the recorded `mod-playerbots` revision above; review it when changing module
revisions rather than applying it blindly.

## Synthetic companion changes

### Canonical controlled roster

Only four persistent characters are bound to the synthetic control plane:

| Character | Class | Role | Governed gathering professions |
| --- | --- | --- | --- |
| Lyra | Mage | party utility, buffs, refreshments, Polymorph | Herbalism 450 |
| Celene | Rogue | Sap, stuns, assignments, economy work | Herbalism 450, Mining 450 |
| Ray | Rogue | normal level-1 companion progression, Combat leveling | Mining 450, Skinning 450 |
| Browntown | Mage | normal level-1 companion progression, Frost leveling | Herbalism 450, Mining 450 |

Ray and Browntown level normally with human players. Max gathering skills are
an explicit supply-role exception; they do not imply free character levels,
combat gear, gold, or replaced professions. Higher-expansion objectives remain
character-level gated.

### Authority and truthful state

The director accepts gameplay orders from a bot's Playerbots master, party or
raid leader, raid assistant, a same-guild Officer or Guild Master, or the
explicitly registered Cadia identity. Guild rank alone never authorizes taking
or transferring the bot's personal gold.

Inventory, equipment, free bag slots, money, guild-bank counts, auction state,
and action outcomes come from worldserver/database observations. Inventory
questions bypass the LLM. A response that claims an unverified item, balance,
deposit, purchase, cast, or completed action is blocked or replaced with a
typed failure/pending result.

### Finite command surface

The implemented intents cover:

- follow, hold, retreat, attack/pull the issuer's selected target, and party
  preparation;
- Polymorph, Sap, stun, Slow Fall, mage burst mode, learned refreshments,
  intellect buffs, and configured portals;
- start/stop farming or economy work, craft one supply operation, collect mail,
  perform one bounded auction operation, deposit eligible materials, and share
  bounded surplus gold; and
- report to the group or continue the bot's existing routine.

The compiled executor revalidates issuer authority, character binding, target,
class, spell/strategy preconditions, combat/death state, guild permissions,
and economic limits. `parameters_json` is currently restricted to `{}`.

### Group-duty behavior

Joining a group no longer causes an automatic summon. A working bot keeps its
routine and asks whether it should report or continue. Only an authorized
explicit answer changes that state. Leaving or being removed from the group
immediately restores the bot's persisted routine.

Controlled personas receive faction-compatible taxi nodes. If ordinary
cross-map travel cannot recover an unattended work objective, the director may
move that bot only to the objective's allowlisted work anchor. This is not a GM
rank and cannot be used as an arbitrary teleport surface.

### Persona and party-chat behavior

Persona prompts were revised to make all four companions loyal, generous,
friendly, and non-condescending. Ray's bounded speech quirk uses “Heh heh” for
deliberate jokes and occasional relaxed banter, never as spam or in urgent
tactical calls.

Party replies use a server broadcast fallback so every human group member sees
the same persona response. Other random Playerbots retain native Playerbots
dialogue and behavior.

## Material-kit and economy automation

The active material mission supplies fixed 1–450 kits for Alchemy,
Inscription, Jewelcrafting, Engineering, and Tailoring. Source URLs,
item entries, quantities, zones, modes, and level gates are fixed in
`synthetic-players/daemon/config/material-kits.yaml`. The LLM may allocate only
qualified workers; it cannot alter the kit or claim progress.

On the recording date:

- material plan 3 was active and the previous plan was marked superseded;
- the active plan contained 109 validated targets; and
- 15 real guild-bank deposit operations had been recorded.

Gathering targets use learned Herbalism, Mining, or Skinning. Cloth and other
loot targets use ordinary mob loot. Auction-only targets remain explicitly
pending procurement. Yellow/green skill-up randomness and daily research or
crafting cooldowns mean the documented quantities are reserves, not a promise
of deterministic 450 completion.

The character-owned auction adapter lists only real tradeable surplus stacks
and buys only Playerbots-classified useful items. Defaults preserve a 100-gold
reserve, cap one-cycle spending at 25 gold, cap a gift at 100 gold, and cap
owned listings at 12. It does not buy the persona's own listing, another
controlled persona's listing, or a same-account listing. Every mutation uses
normal AzerothCore persistence and writes an economy-ledger row.

AHBot Plus is a separate realm-liquidity layer. It creates synthetic market
supply by design; it must not be confused with a persona's real inventory or
profession work.

## Novice Death Knight module

The optional module enrolls only Death Knights created while it is enabled. It
starts enrolled characters at level 1 in their racial area, provides a staged
ability curve, normal talents from level 10, level-1 equipment, low-level
server-side spell scaling, and the stock Death Knight transition at level 55.
Existing Death Knights are not silently changed, and internal-session
Playerbots are excluded unless an operator deliberately changes that boundary.

The tracked `.conf.dist` remains disabled so installing the source cannot alter
a realm merely by being present. The current private deployment explicitly
enables it. Disable new enrollment and module behavior with:

```ini
NoviceDeathKnight.Enable = 0
```

Disabling is non-destructive: enrollment audit rows remain, and already
enrolled characters resume module behavior if it is re-enabled. Full install,
ability staging, database migration, and rollback details are in
[`novice-death-knight/README.md`](./novice-death-knight/README.md).

## Client compatibility and known faults

Use a clean 3.3.5a build-12340 client as the base and preserve a recoverable
copy before applying client patches.

- All-race/all-class characters require the matching `mod-arac` client patch.
  A server-only install may create characters the stock client cannot render or
  select correctly.
- The custom level-255 shield/equipment set requires its generated `Item.dbc`
  patch for client-side shield checks. See
  [`gm-level-255/README.md`](./gm-level-255/README.md).
- The stock client's barber-cost DBC has only 100 level rows. Opening the
  barbershop on a level-255 character can dereference a missing row and crash in
  `GetBarberShopTotalCost`. Until a reviewed client MPQ extends that DBC, avoid
  the barber chair at level 255 and use the server's character-customization
  flow from the login screen.
- A crash may leave Gamescope, Wine, wineserver, and crash-reporter wrappers
  alive. Stop only the stale client process tree before relaunching; do not stop
  the realm containers or unrelated GPU/model services. Single-instance
  launcher hardening remains future work.

## Validation evidence

The following checks were performed against the source and live deployment on
2026-08-29:

- all Synthetic Players Python tests passed (`57 passed`);
- the deployed Cadia Player Director and Novice Death Knight C++ sources match
  the copies tracked here;
- both modules compiled into the running worldserver during the controlled
  rebuild;
- auth, database, and worldserver containers were running, and the database
  health check was healthy;
- the local persona model endpoint and event-driven daemon were running;
- Playerbots repeatedly reported 500 random bots online;
- Lyra, Celene, Ray, and Browntown were online with the gathering skills shown
  above; and
- plan 3, its 109 targets, and 15 persisted guild-bank deposits were observed
  directly in the characters database.

These observations are evidence from one point in time, not configuration
authority. Re-run the checks after rebuilds, migrations, module updates, or
population changes.

## Known limitations and follow-up

- At the configured 500-bot boundary Playerbots has also emitted an account
  capacity warning requesting one additional bot account. The population was
  online, but the warning should be resolved before increasing the target.
- Typed action support is broader than the original chat-only prototype, but
  Playerbots still owns pathfinding, rotations, encounter strategies, and
  moment-to-moment gameplay.
- A spell or item can be known server-side yet unusable if the 3.3.5a client
  lacks matching DBC data or the character fails class/equipment/range/reagent
  preconditions.
- Material plans prove bank coverage and executor outcomes. They do not prove a
  human crafter has received every random skill-up.
- The current launcher cleanup was manual. A safe PID/prefix-scoped
  single-instance guard remains to be implemented and tested.

## Rebuild, restart, and rollback boundary

Schema initialization is additive and idempotent. A C++ module or Playerbots
patch requires a rebuild; Lua and daemon changes do not by themselves require a
worldserver rebuild.

Generic Docker sequence after installing module source:

```bash
cd /absolute/path/to/azerothcore
docker compose build ac-worldserver ac-db-import
docker compose run --rm --no-deps ac-db-import
docker compose up -d --no-deps --force-recreate ac-worldserver
```

Before changing deployment state, take normal database and configuration
backups. Reversal is bounded:

- stop the Synthetic Players daemon to remove LLM dialogue/planning while
  leaving native Playerbots functional;
- disable ALE to stop the Lua event/action bridge;
- disable the director module in its config and rebuild/remove it if the typed
  executor must be eliminated;
- set `NoviceDeathKnight.Enable = 0` to stop its behavior without deleting
  characters;
- disable AHBot Plus buyer/seller independently from character-owned economy
  profiles; and
- reverse the level-255 Playerbots patch only after removing the level-255
  condition or accepting the original freeze risk.

Never delete character, auction, guild-bank, or synthetic audit tables as a
casual rollback.

## Authorization and provenance

The implementation, controlled rebuild/restart, documentation, commit, and
push were authorized by the owner through explicit instructions in the
authenticated working conversation. Decision authority belongs to the owner;
OpenAI Codex is the implementation and recording agent. This record was
completed after implementation and live validation on 2026-08-29. It does not
broaden authority to publish credentials, private conversations, account data,
or network configuration.
