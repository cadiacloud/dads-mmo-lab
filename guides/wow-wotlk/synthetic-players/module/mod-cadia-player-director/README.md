# Cadia Player Director AzerothCore Module

This module is the trusted in-world executor for Synthetic Players high-level
intents. It depends on `mod-playerbots` and must be compiled statically into the
same worldserver. Configuration fails if Playerbots is disabled or this module
is assigned dynamic linkage.

The module does not call an LLM and exposes no network listener. It consumes
only rows from `acore_characters.synthetic_intents`, validates the real online
issuer and canonical persona binding, requires Playerbots
master/leader/assistant authority, same-guild Officer-or-higher authority, or
explicit Cadia authority,
maps one enum to a hard-coded Playerbots action, and records the observed result.

Guild rank authority is deliberately not sufficient for `SHARE_GOLD`. An
Officer or Guild Master can direct the bot's gameplay and economy work, but
cannot use guild rank alone to make the bot transfer its personal gold.

For the persistent level-1 personas, the same trusted module applies the
installed Playerbots premade talent templates when talent points become
available: Combat PvE for Ray and Frost PvE for Browntown. This is level-gated
progression, not a level, spell, gear, or gold boost.

## Intent catalog

| Intent | Playerbots operation | Verified outcome |
| --- | --- | --- |
| `FOLLOW` | `follow chat shortcut` | `follow` strategy active |
| `HOLD_POSITION` | `stay chat shortcut` | `stay` strategy active |
| `ATTACK_PLAYER_TARGET` | direct validated Playerbots target | selected hostile engaged or defeated |
| `PULL_PLAYER_TARGET` | `pull my target` | standard pull engages or defeats target |
| `RETREAT` | `flee chat shortcut` | passive retreat strategy active |
| `PREPARE_PARTY` | class preparation strategy | `buff` or paladin `bkings` strategy active |
| `POLYMORPH_PLAYER_TARGET` | mage Polymorph | selected target polymorphed |
| `SAP_PLAYER_TARGET` | moon CC assignment plus rogue `cc` strategy | selected target sapped |
| `STUN_PLAYER_TARGET` | Kidney Shot, Cheap Shot, or rogue opener | selected target stunned |
| `SLOW_FALL_ISSUER` | mage Slow Fall | issuer has aura |
| `POWER_UP` | class/spec `boost` strategy | boost strategy active |
| `START_FARMING` | noncombat `grind` plus `gather` | both strategies active |
| `STOP_FARMING` | remove farm strategies and follow | farm strategies absent, follow active |
| `START_ECONOMY` | enable bounded profile and gathering | profile enabled and farm strategies active |
| `STOP_ECONOMY` | disable bounded profile and regroup | profile disabled and follow active |
| `WORK_AUCTION_HOUSE` | list one real surplus stack or buy one useful listing | persisted auction or purchase mail |
| `CRAFT_SUPPLIES` | Playerbots `craft random item` | profession-aware craft action accepted |
| `COLLECT_MAIL` | Playerbots `mail take *` | delivered-mail count decreases |
| `DEPOSIT_GUILD_BANK` | drain eligible gathered stacks through the Guild API | persisted guild-bank contents and profession ledger rows |
| `SHARE_GOLD` | mail a bounded share of surplus to issuer | real balance deduction and normal mail |
| `REPORT_TO_GROUP` | explicit report decision; bounded move to issuer if required | reporting mode and follow active |
| `CONTINUE_ROUTINE` | retain autonomous material work while grouped | routine mode and work strategies active |

`parameters_json` must currently be exactly `{}`. Unknown intents, arbitrary
parameters, offline actors, noncanonical bindings, unauthorized bot issuers,
players who are neither group-authorized nor same-guild Officers, insufficient
Playerbots authority, dead bots, and invalid targets are
rejected with typed result codes.

Economy profiles default to a 100-gold reserve, 25-gold purchase limit per
cycle, 100-gold gift cap, and 12 owned auctions. Listings move the character's
exact tradeable `ITEM_USAGE_AH` stack into AzerothCore's auction persistence.
Purchases are restricted to Playerbots-classified equipment upgrades,
profession inputs, usable items, and ammunition. Background cycles pause while
the character has a game-client master, is dead, or is in combat. Every
successful economy mutation is recorded in `synthetic_economy_ledger`.

## Governed profession objectives

The older `plan-professions` workflow remains available for normal skill
progression experiments. It is not the active real-player-kit policy.

`synthetic-daemon plan-professions --activate` makes one bounded LLM call per
controlled bot/profession pair to choose a zone for every fixed 1–450 Mining,
Herbalism, or Skinning guide stage.
The output is JSON-schema constrained, then rejected unless every bot,
profession, stage, and zone exactly matches the local allowlist in
`config/profession-guides.yaml`. The LLM cannot change skill ranges, train a
profession, grant skill points, create materials, alter guild-bank policy, or
send arbitrary Playerbots commands.

This module executes the validated rows. An unattended controlled persona
travels to the selected guide zone and enables native Playerbots `travel`,
`grind`, and `gather` strategies. A bot actively led by a real player stays with
the group and only enables gathering. The executor can train the next gathering
rank after the normal WotLK skill and character-level gates and provision only
a mining pick or skinning knife. It never raises the current gathering skill.
Only one profession objective runs per bot at a time; the lowest observed skill
runs first so multiple professions cannot overwrite each other's travel target.
When Playerbots has no prebuilt travel destination for a selected zone, the
module derives a persistent native route from an actual gatherable node or
skinnable creature spawn in that allowlisted zone; it does not teleport the bot.
For pooled ore and herb locations, the executor then scans the loaded world and
retargets travel to a currently spawned, skill-valid node before invoking the
native Playerbots loot/move/open actions. The module migration also installs one
normal, non-pooled Durotar Copper Vein as a reproducible skill-1 bootstrap and
acceptance-test node; it uses normal core loot, skill-up, and respawn rules.

Eligible gathered ore, stone, gems, herbs, leather, and elemental gathering
reagents are deposited into guild-bank tab 0 through AzerothCore's Guild API,
subject to the bot's real deposit rights and available bank space. Deposits run
promptly whenever an eligible stack appears and again while draining materials
at stage completion. An authorized leader may also say “deposit your ore into
the guild bank” to enqueue `DEPOSIT_GUILD_BANK`; the executor immediately drains
all eligible gathering categories defined by the bot's active governed plan.
Every rank, tool, deposit, and stage-completion result is recorded in
`synthetic_profession_ledger`.

Create or refresh a plan from the daemon directory:

```bash
.venv/bin/synthetic-daemon init-db
.venv/bin/synthetic-daemon plan-professions --activate \
  --model cadia_persona --api-base http://127.0.0.1:8098/v1
```

The planner is event-driven: no LLM heartbeat or idle inference is added. Once
the plan is stored, native deterministic code performs and audits the work.

## Material-kit routine and group duty

`plan-material-kits` supersedes active skill-leveling objectives. On login the
module maxes only Herbalism, Mining, or Skinning already learned by Lyra,
Celene, Ray, or Browntown, provisions the ordinary gathering tool, and grants
all faction-compatible taxi nodes. RandomBot `teleport` and `randomize` events
are continuously deferred for those four bindings so autonomous population
management cannot relocate or rebuild them.

Each target carries an exact item entry, cumulative guild-bank threshold,
qualified bot, acquisition mode, allowlisted zone, minimum character level, and
source URL. The executor uses actual `guild_bank_item` and `item_instance`
counts, deposits only actual matching inventory stacks, and never treats LLM
dialogue as evidence. Low-level Ray and Browntown remain gated from
Outland/Northrend targets until their real character level is sufficient.

When a persona accepts a group invitation it continues its routine and asks:
“Should I report to you now, or keep working?” `AiPlayerbot.SummonWhenGroup` is
disabled for this deployment. Only an explicit `REPORT_TO_GROUP` answer permits
a bounded move to the group; `CONTINUE_ROUTINE` retains work. Dropping group
immediately restores `travel`, `grind`, `gather`, and `loot`. Cross-map work
recovery may teleport only to the persisted target's allowlisted work anchor;
it confers no GM account security.

## Installation boundary

From the Dad's MMO Lab repository:

```bash
./guides/wow-wotlk/synthetic-players/install-player-director.sh \
  --server-root /absolute/path/to/azerothcore
```

Then initialize the database schema from the daemon, rebuild the worldserver,
and perform a controlled restart. Installing the source alone does not modify a
running realm.

The module's `.conf.dist` is copied into the normal AzerothCore module config
installation path during the build. Its default polling and snapshot paths are
database-only; never expose Playerbots' unauthenticated command-server port as
an alternative control plane.
