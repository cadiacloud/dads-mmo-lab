# Controlled Persona Bots: Synthetic Player Operations

Status: implemented source and deployment guide

Game target: AzerothCore / Playerbots, Wrath of the Lich King 3.3.5a

Persona scope: Lyra, Celene, Ray, and Browntown

## 1. Runtime contract

Lyra, Celene, Ray, and Browntown are the only Playerbots whose chat is routed
through the local persona model. Every other Playerbot remains under the native
deterministic Playerbots engine.

The model chooses dialogue and may propose one typed, high-level intent. It does
not issue raw commands, spell IDs, SQL, GM commands, or frame-by-frame movement.
The worldserver module authorizes the issuer, executes a known Playerbots action,
verifies the observable result, and returns a grounded success or failure message.

There is no idle LLM heartbeat. MySQL queues and worldserver state snapshots are
polled while idle, but model inference occurs only for an accepted game event.

## 2. Authority order

An action is accepted when the issuer is one of:

1. the bot's current Playerbots master in its party or raid;
2. the party or raid leader;
3. a raid assistant;
4. an Officer or Guild Master in the bot's current guild, even when not grouped;
   or
5. a character explicitly recorded as enabled role `CADIA` in
   `synthetic_command_authorities`.

The Cadia table is deliberately empty by default. Add a character only after the
in-game Cadia identity exists and its GUID has been verified. Explicit Cadia
authority may operate outside the group. Dialogue from ordinary guild or group
members is allowed; mechanical orders from them are rejected unless one of the
rules above applies. Guild rank alone never authorizes `SHARE_GOLD`; an Officer
or Guild Master cannot use that rank to take a persona bot's personal gold.

## 3. Commands available now

Address the intended bot in party chat—`Lyra, ...`, `Celene, ...`, `Ray, ...`,
`Browntown, ...`, or an `@Name` mention—or whisper the bot directly.

| Persona | Example request | Trusted action | Verification |
|---|---|---|---|
| Lyra | `sheep my target` | cast Polymorph on issuer's selected hostile target | target is polymorphed |
| Lyra | `cast slow fall` | cast Slow Fall on issuer | issuer has Slow Fall |
| Lyra | `power up` | enable the class/spec boost strategy | boost strategy active |
| Lyra | `make a mage table` | highest known Ritual of Refreshment | table gameobject observed |
| Lyra | `buff the party` | highest known Arcane Brilliance | aura observed |
| Lyra | `portal to Dalaran` | known, allowlisted portal spell | portal gameobject observed |
| Celene | `sap my target` | mark target as moon CC, enable rogue CC behavior | target has Sap mechanic |
| Celene | `stun my target` | Kidney Shot, Cheap Shot, or a verified rogue opener | target enters stunned state |
| Ray | `sap my target` | mark target as moon CC, enable rogue CC behavior | target has Sap mechanic |
| Browntown | `sheep my target` | cast Polymorph on issuer's selected hostile target | target is polymorphed |
| Either | `attack my target` | direct Playerbots combat target | combat engagement or death |
| Either | `pull my target` | Playerbots pull request using issuer's target | combat engagement or death |
| Either | `follow me`, `hold here`, `fall back` | Playerbots movement strategy | strategy active |
| Either | `go farm and gather` | enable grind and gathering strategies | both strategies active |
| Either | `stop farming` | disable grind/gather and regroup | follow active, farm strategies absent |
| Either | `start economy work` | enable bounded background list/buy/craft cycles | profile enabled and farm strategies active |
| Either | `work the auction house` | list owned surplus or buy one useful listing | persisted auction or purchase mail |
| Either | `craft something useful` | Playerbots profession-aware random craft | crafting action accepted |
| Either | `collect your mail` | Playerbots mailbox collection | delivered-mail count decreases |
| Either | `share some gold with me` | mail a bounded share of surplus to issuer | money deducted and normal mail created |
| Either | `stop economy work` | disable background economy cycle and regroup | profile disabled and follow active |

A request can still fail honestly: wrong class, unknown spell, invalid or immune
target, combat restrictions, range/line of sight, missing reagent, missing
profession skill, or verification timeout.

## 4. Lyra progression policy

Primary endgame plan: Fire/TTW once gear supplies the required caps and enough
crit to make the specialization work. Do not blindly copy a best-in-slot list;
recompute around actual raid buffs, current gear, and available items.

Stat policy:

1. reach the applicable hit cap;
2. spell power;
3. critical strike;
4. haste;
5. spirit/intellect as secondary values.

The Fire guide identifies 17% total spell hit, or 14% from gear when the raid
supplies the common 3% spell-hit debuff (367 hit rating), and recommends
gear-aware simulation. Phase 4 gear planning centers on ICC/Tier 10 pieces rather
than treating a static list as universally correct.

Endgame performance professions: Engineering and Tailoring. Engineering supplies
Hyperspeed Accelerators, Nitro Boosts, and explosives; Tailoring supplies
Lightweave Embroidery. Profession replacement is never automatic.

Sources:

- [Wowhead Fire Mage PvE overview](https://www.wowhead.com/wotlk/guide/classes/mage/fire/dps-overview-pve)
- [Wowhead Fire Mage stat priority](https://www.wowhead.com/wotlk/guide/classes/mage/fire/dps-stat-priority-attributes-pve)
- [Wowhead Fire Mage Phase 4 BiS](https://www.wowhead.com/wotlk/guide/classes/mage/fire/dps-bis-gear-pve-phase-4)

## 5. Celene progression policy

Primary endgame plan: Combat Rogue. Cap-aware evaluation comes before item-level
or a blind BiS list: first solve special-attack/poison hit and expertise needs,
then value agility and attack power, with armor penetration becoming much more
valuable as late-ICC gear accumulates. Avoid overcapping expertise, hit, or crit.

Staged profession plan:

1. Mining plus Engineering while the server economy needs ore and Celene builds a
   material reserve;
2. propose—not automatically execute—a transition from Mining to Jewelcrafting
   when the reserve and auction supply are healthy;
3. final performance target: Engineering plus Jewelcrafting.

Sources:

- [Wowhead Combat Rogue PvE overview](https://www.wowhead.com/wotlk/guide/classes/rogue/combat/dps-overview-pve)
- [Wowhead Combat Rogue stat priority](https://www.wowhead.com/wotlk/guide/classes/rogue/combat/dps-stat-priority-attributes-pve)
- [Wowhead Combat Rogue Phase 4 BiS](https://www.wowhead.com/wotlk/guide/classes/rogue/combat/dps-bis-gear-pve-phase-4)
- [Wowhead Combat Rogue Phase 4 pre-raid gear](https://www.wowhead.com/wotlk/guide/classes/rogue/combat/dps-bis-gear-pre-raid-pve-p4)

## 6. Ray and Browntown leveling policy

Ray and Browntown are persistent same-account altbots designed to level beside
the real-player group. They begin at level 1 with normal starter equipment and
no granted XP or gold. Use `.playerbots bot add Ray` and
`.playerbots bot add Browntown` from an active ADMIN character; the server logs
them in as in-process bots while the real client remains on the current
character.

Ray follows Combat PvE from level 10, favors a slow main hand and fast off hand,
and prefers an axe when otherwise equivalent to use Orc Axe Specialization. His
permanent professions are Mining and Skinning. His friendly speech quirk is
`Heh heh`: he uses it for deliberate jokes and occasionally in relaxed banter,
but not in every response or urgent tactical callout.

Browntown follows Frost PvE from level 10 for safe, controlled leveling. Her
permanent professions are Herbalism and Mining. She prioritizes assigned
Polymorph, learned refreshments, and the applicable intellect buff. Any later
endgame spec change remains a cap-aware proposal based on real gear, not an
automatic boost.

## 7. Economy participation

### Active 1–450 material-kit mission

The persona bots are suppliers for real players, not consumers of leveling
kits. Their existing gathering professions are provisioned to 450/450. The
active plan covers Alchemy, Inscription, Jewelcrafting, Engineering, and
Tailoring using the fixed catalog in `daemon/config/material-kits.yaml` and the
five cited WoW-Professions WotLK guides. The LLM allocates qualified workers;
compiled code owns movement, level gates, real bag inspection, exact deposits,
and cumulative guild-bank counts.

Lyra supplies Herbalism. Celene supplies Herbalism and Mining. Ray supplies
Mining and Skinning; Browntown supplies Herbalism and Mining. Ray and Browntown
still level normally with the human group, so high-expansion targets wait for
their real character level. Cloth is ordinary mob loot. Arcane Dust and
Infinite Dust are tracked as auction procurement and are not described as
harvested until real bank contents prove the target.

The five plans also record a fixed finishing route. Alchemy uses Frost Wyrm
flasks, Jewelcrafting uses Earthsiege meta gems, Engineering uses Gnomish Army
Knives, Inscription uses recurring Northrend research, and Tailoring reserves
materials for 40 additional Frostweave Bags. Because several guide steps are
yellow/green or cooldown-bound, the bank target is a source-backed reserve and
may need a refill; the LLM is not allowed to conceal or revise that fact.

Invitation policy is “continue and ask”: joining a group never summons the bot.
The bot asks whether to report or keep working, obeys an explicit answer from an
authorized group leader/assistant or guild Officer/GM, and resumes the kit
routine immediately after leaving the group.

### Native Playerbots features to keep enabled

The current Playerbots configuration supports:

- class-matching profession assignment with
  `AiPlayerbot.ClassMatchingProfessionChance`;
- nearby gathering through the `gather` strategy;
- ordinary looting, vendor buying/selling, repair, trainer use, crafting, questing,
  travel, and RPG behavior;
- direct bot/player trade through `AiPlayerbot.EnableRandomBotTrading = 1`;
- automatic trade for linked items through
  `AiPlayerbot.EnableAutoTradeOnItemMention = 1`; and
- mail through `AiPlayerbot.BotSendMailEnabled = 1`.

For a crafting economy, also make deliberate decisions about recipe rolls and
disenchant rolls. The current defaults
`AiPlayerbot.LootRollRecipe = 0` and
`AiPlayerbot.LootRollDisenchant = 0` do not make bots strong recipe or
disenchant participants. Change those only after testing loot fairness with
human players.

The `START_FARMING` intent enables `grind` plus `gather` for a controlled persona. It
does not grant a profession, invent a route, create materials, or guarantee a
nearby node. `START_ECONOMY` also enables the persisted bounded economy profile.
The worldserver pauses background economy cycles while a human has the bot as an
active game-client master, and while the bot is dead or in combat.

`DEPOSIT_GUILD_BANK` is the immediate, leader-directed deposit operation. It
drains real eligible gathering stacks from the named bot's bags into the first
guild-bank tab through AzerothCore's Guild API. The bot must share the issuer's
group, the issuer must be master/leader/assistant/Cadia-authorized, the bot must
be alive and out of combat, and the bot's guild rank must have deposit rights.
The completion reply is derived from the executor result—not from an LLM claim.

### Character-owned auction-house work

This Playerbots branch contains an old, commented-out
`StoreLootAction::AuctionItem`; it is not used. The Cadia Player Director now
provides a separate bounded adapter. Controlled personas:

- list only an actual, tradeable inventory stack classified by Playerbots as
  surplus (`ITEM_USAGE_AH`), moving that exact item into the auction system;
- undercut the lowest matching buyout by one percent, or use a conservative
  vendor-price fallback;
- buy only actual listings that Playerbots classifies as an equipment upgrade,
  profession input, usable item, or ammunition;
- never buy their own listing, another controlled persona's listing, or a
  listing owned by the same account;
- preserve a 100-gold reserve, spend at most 25 gold in one cycle, and own at
  most 12 listings by default; and
- use normal AzerothCore deposit, mail, sale, and persistence paths, with an
  additional row in `synthetic_economy_ledger`.

These limits live in `synthetic_economy_profiles` and can be changed per
character without expanding the executable intent catalog. An explicit AH
request performs at most one listing or purchase. An idle enabled profile runs
at most one list, buy, or craft operation per configured economy interval.

The realm-wide liquidity layer is the official AzerothCore
[mod-ah-bot](https://github.com/azerothcore/mod-ah-bot). The reviewed revision for
this deployment is `a680cc1c98290713e9b3d3289544af78e5186dc1`. It seeds ordinary
loot and profession inputs and can buy real character listings. It runs through
a dedicated, locked, non-login service principal—not a persona bot. Auctions
whose owner is a controlled persona were created by the character-owned adapter; the
market maker merely supplies liquidity and may become their counterparty.

To deploy it safely:

1. pin and record the reviewed revision;
2. create a dedicated locked, non-GM, non-login economy identity, not Lyra or
   Celene;
3. rebuild AzerothCore with the module;
4. import its world SQL;
5. configure conservative per-cycle counts, duplicate limits, and safe item
   filters;
6. mount the reviewed config read-only into the worldserver;
7. enable seller and buyer only after the world SQL and identity are verified;
8. inspect auction counts, item mix, prices, mail, and persona economy ledger
   after restart.

The market maker creates synthetic supply by design. The persona adapter does
not: its listings, purchases, deposits, gold gifts, and mail always mutate the
bound character's real state.

## 8. Addons for a 3.3.5a client

Addons improve the human interface but do not grant server-side bot abilities.
Use files that explicitly support the 3.3.5 client API:

- [oRA3 r452 (3.3.5)](https://www.curseforge.com/wow/addons/ora3/files/464284)
  for raid coordination;
- [AuctionLite 3.3.5 release](https://www.curseforge.com/wow/addons/auctionlite/files/477910)
  for human AH browsing;
- [KPack 3.3.5](https://www.curseforge.com/wow/addons/kpack) or
  [MultiFollow 3.3.5](https://www.curseforge.com/wow/addons/multifollow-3-3-5-addon)
  for optional legacy quality-of-life tools.

Modern WoW Classic addons—even when labeled “Wrath”—may target the 3.4.x Classic
API and are not automatically compatible with the private-server 3.3.5a client.
The authoritative assignment inputs remain normal raid markers, party/raid
leadership, assistants, and explicit addressed chat.

## 9. Governance and persistence

- Persona dialogue is not action evidence.
- Every typed intent records lifecycle events and a terminal result code.
- Gear/spec/profession plans are candidate records in
  `synthetic_progression_plans`.
- Farming routes and longer trade plans may be candidate records in
  `synthetic_economy_goals`; they do not execute merely because a row exists.
- The owner authorized the bounded economy executor in the authenticated working
  conversation on 2026-08-25. That authorization covers the limits above; it
  does not implement profession replacement, arbitrary purchases, or unbounded
  transfers.
- Character bindings are canonical by name, GUID, race, class, and gender; a
  mismatch stops the daemon rather than controlling the wrong bot.
