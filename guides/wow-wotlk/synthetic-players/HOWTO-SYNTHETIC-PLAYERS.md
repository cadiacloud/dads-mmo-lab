# 🧠 Dad's MMO Lab: Synthetic Players — How-To Guide
## Local LLM Persona and Playerbots Director Bridge for AzerothCore WoW (WotLK 3.3.5a)

Add local-LLM dialogue, personality, conversational memory, bounded actions,
and typed high-level direction to real AzerothCore Playerbot characters. The
LLM chooses a goal at decision boundaries; Playerbots retains movement,
pathfinding, combat reactions, rotations, and encounter mechanics.

---

## 🏛️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    AzerothCore Server                       │
│                                                             │
│  ┌───────────────────────┐       ┌───────────────────────┐  │
│  │    mod-playerbots     │◄──────│ mod-cadia-player-     │  │
│  │ (Movement, Combat AI) │       │ director (Executor)   │  │
│  └───────────┬───────────┘       └───────────▲───────────┘  │
│              │       ┌───────────────────────┴───────────┐  │
│              │       │  SyntheticPlayers.lua            │  │
│              │       │  (ALE Event, Chat, Mage Actions) │  │
│              │       └───────────────────────┬───────────┘  │
└──────────────┼───────────────────────────────┼──────────────┘
               │                               │
               ▼                               ▼
 [inbox / outbox / intents / intent_events / bot_state]
                               ▲
                               │ Async MySQL Poller (500ms)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│               Synthetic Players Python Daemon               │
│                                                             │
│  - Persona Manager (Lore-grounded archetypes & styles)      │
│  - Conversational & Relationship Memory (Rolling buffers)   │
│  - Bounded Presentation Action Parser ([ACTION: ...])       │
│  - Typed High-Level Intent Router ([INTENT: ...])            │
│  - Deterministic Verified-Result Replies                    │
└──────────────────────────────┬──────────────────────────────┘
                               │ OpenAI-Compatible API
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                vLLM Server (Local Gemma 4)                  │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚡ Key Features

1. **In-Game Whispers & Chat:** Whisper Lyra, Celene, Ray, or Browntown, or address one in Party/Say/Guild chat; those four canonical bots reply in-character. Other Playerbots retain native AI.
2. **Context-Aware:** Replies include the speaker, bot identity, class/race, current zone, and recent conversation context.
3. **World Event Reactions:** Grouped bots can comment on elite/boss kills, player deaths, level-ups, achievements, and targeted emotes.
4. **Bounded Actions:** A reply may make the bot emote, change posture, or ask a mage to cast one of a finite set of known portal spells. Combat strategy and arbitrary Playerbots, server, shell, or database commands are not delegated to the LLM.
5. **Low-Impact Queueing:** The database inbox/outbox decouples model latency from the world thread. Operators must still monitor database and ALE latency under load.
6. **Action Audit:** `synthetic_action_audit` records whether a bounded action was accepted or rejected independently from chat-delivery status, without duplicating the conversation text.
7. **Playerbots Direction:** A finite typed-intent catalog covers movement, selected-target combat, crowd control, Slow Fall, burst mode, farming, and bounded economy work without exposing arbitrary commands.
8. **Verified Replies:** Gameplay orders do not produce a completion claim until the worldserver records a terminal result. The result reply comes from a fixed result-code map rather than fresh model prose.

### Privacy and retention

This prototype processes player chat and stores queue rows plus selected memory
summaries in `acore_characters`. Its normal logs also identify the responding
bot and player. Treat the database, daemon logs, and persona bindings as private
game-session data: restrict access, define retention, and do not publish raw
conversation records. The action-audit table intentionally stores the typed
action and outcome without copying dialogue text. Director rows reference the
original inbox event and retain typed lifecycle evidence rather than another
copy of the conversation.

---

## 🚀 Quick Setup Guide

### Step 1: Install Python Daemon Dependencies

We recommend using [`uv`](https://github.com/astral-sh/uv) or standard Python `venv`:

```bash
cd guides/wow-wotlk/synthetic-players/daemon
uv venv
source .venv/bin/activate
uv pip install -e .
```

### Step 2: Initialize Database Tables

Ensure your AzerothCore MySQL database container (`ac-database`) is running, then initialize the synthetic tables:

```bash
# Option A: Using the CLI
synthetic-daemon init-db

# Option B: Direct MySQL import
docker exec -i ac-database sh -lc \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot acore_characters' \
  < ../sql/synthetic_schema.sql
```

### Step 3: Deploy the ALE Lua Bridge

Copy the Lua bridge script into your worldserver's `lua_scripts` directory:

```bash
# Standard DML server path:
cp ../lua/SyntheticPlayers.lua ~/wow-server-playerbots/env/dist/etc/modules/lua_scripts/
```

Enable ALE and point it at that directory. For Docker Compose, the relevant environment variables are:

```yaml
AC_ALE_ENABLED: "1"
AC_ALE_SCRIPT_PATH: "/azerothcore/env/dist/etc/modules/lua_scripts"
```

If your server is currently running, reload ALE in the GM console:
```text
.reload ale
```

### Step 4: Install the Playerbots Director

Install the trusted Playerbots executor source into the AzerothCore tree:

```bash
cd guides/wow-wotlk/synthetic-players
./install-player-director.sh --server-root /absolute/path/to/azerothcore
```

The module depends on `mod-playerbots` and must be compiled statically into the
same worldserver. Initialize the schema before starting that build. A rebuild
and controlled worldserver restart are required; copying the source does not
alter a running realm. See
[`module/mod-cadia-player-director/README.md`](module/mod-cadia-player-director/README.md)
for the exact executor boundary.

### Step 5: Launch vLLM with Gemma 4

Start your local vLLM instance serving your Gemma 4 model:

```bash
vllm serve /path/to/your/model \
    --host 127.0.0.1 \
    --port 8000 \
    --tensor-parallel-size 1 \
    --gpu-memory-utilization 0.90 \
    --max-model-len 4096
```

### Step 6: Start the Synthetic Players Daemon

In a separate terminal or background screen/service:

```bash
synthetic-daemon run --model your-served-model --api-base http://127.0.0.1:8000/v1
```

---

## 🎮 In-Game Interaction

### Canonical persona roster in the current deployment

These names are real, persistent Playerbot characters in the current server database, not prompt-only aliases:

| Name | Race | Class | Persona role |
| --- | --- | --- | --- |
| Lyra | Blood Elf | Mage | Warm arcane scholar, party utility, sheep assignments |
| Celene | Blood Elf | Rogue | Loyal field operative, sap/stun assignments, gathering |
| Ray | Orc | Rogue | Persistent level-1 friend, Combat leveling, Mining/Skinning |
| Browntown | Orc | Mage | Persistent level-1 friend, Frost leveling, Herbalism/Mining |

Ray and Browntown are long-progression altbots on the ADMIN account. A real
client logs into the account's active character; Playerbots then instantiates
the other same-account characters inside the worldserver without a second game
client or account session. Add them from an active ADMIN character with:

```text
.playerbots bot add Ray
.playerbots bot add Browntown
```

They begin at level 1, receive no free experience, gear, or gold, and level
through normal play with the group. At level 10 and later level gains, the
trusted worldserver module applies Ray's Combat PvE and Browntown's Frost PvE
premade Playerbots templates when talent points are available. The active
level-gated spell-learning module supplies only spells appropriate to their
actual level.

`synthetic_persona_bindings` binds each persona name to one character GUID and records that character's original name, race, class, and gender. The daemon validates every binding at startup and rejects an event whose target GUID does not match the named persona. This prevents a prompt or forged queue record from impersonating a canonical persona.

The division of responsibility is explicit:

- The local LLM supplies dialogue, persona voice, conversational context, and typed requests from the bounded action and intent catalogs.
- `mod-playerbots` supplies movement, combat, targeting, pathfinding, spell use, loot, and normal game behavior.
- `SyntheticPlayers.lua` carries real in-game events to the daemon and delivers the generated response through the bound Playerbot object.
- `mod-cadia-player-director` authorizes high-level intents and maps them to existing Playerbots strategies/actions inside the worldserver.

The mage capability handlers are narrow exceptions to ordinary Playerbots spell
control. The daemon accepts only the finite actions below. ALE verifies the
bound character, class, group membership, combat state, and known spell before
starting a normal non-triggered cast. It does not accept arbitrary spell IDs or
commands.

| Action | Result | Verification |
| --- | --- | --- |
| `PORTAL <DESTINATION>` | Cast a configured mage portal | Expected portal gameobject appears nearby |
| `REFRESHMENT` | Cast the highest known Ritual of Refreshment | Expected refreshment table appears nearby |
| `BUFF ARCANE BRILLIANCE` | Cast the highest known Arcane Brilliance | Equivalent party aura appears |

Explicit player wording such as “please make water” is also routed through a
deterministic intent matcher. The LLM still writes the in-character response,
but a clear mechanical request does not depend on the model remembering an
action tag. The response is phrased as an attempt until ALE records a verified
outcome.

### 1. Whispering a Bot
Send an in-game whisper to an online controlled persona bot:
```text
/w Celene What do you think of this dungeon?
```
**Celene replies briefly in character.** Conversation does not itself authorize an action.

### 2. Party & Group Banter
In party chat with at least one online Playerbot, use `@Name` to choose a specific persona. Without a mention, the first Playerbot in the group receives the event:
```text
/p @Lyra, do you have extra water before we pull the boss?
```
**Lyra replies:**
> *"Of course. Give me a moment and I’ll set the table for everyone."*

### 3. Bounded Actions

For a grouped mage companion, request a specific destination:

```text
/w Lyra Please open a portal to Orgrimmar for us.
```

Supported portal destinations are Stormwind, Ironforge, Darnassus, Exodar,
Theramore, Orgrimmar, Undercity, Thunder Bluff, Silvermoon, Stonard, Shattrath,
and Dalaran. The mage must actually know the faction-appropriate spell and
have the normal game requirements. An unclear destination causes a clarification
instead of a random portal.

For food and water, ask a grouped mage to make refreshments or set a mage
table. The bridge uses the highest known WotLK Ritual of Refreshment rank; party
members collect the level-appropriate food and water from the normal gameobject.
For the intellect group buff, ask for buffs, intellect, or Arcane Brilliance.

The action audit uses `requested`, `verified`, `failed`, and `rejected` as
distinct outcomes. A friendly line of dialogue is never proof that a spell
completed.

### 4. High-level Playerbots direction

The director accepts only this catalog:

| Intent | Example player wording | Verified executor result |
| --- | --- | --- |
| `FOLLOW` | “Lyra, follow me.” | Playerbots `follow` strategy active |
| `HOLD_POSITION` | “Stay here and hold this position.” | `stay` strategy active |
| `ATTACK_PLAYER_TARGET` | “Attack my target.” | Selected hostile engaged or defeated |
| `PULL_PLAYER_TARGET` | “Pull this mob back.” | Standard Playerbots pull engages or defeats it |
| `RETREAT` | “Fall back.” | Passive retreat strategy active |
| `PREPARE_PARTY` | “Buff up and get ready.” | Supported class preparation strategy active |
| `POLYMORPH_PLAYER_TARGET` | “Lyra, sheep my target.” | Selected hostile is polymorphed |
| `SAP_PLAYER_TARGET` | “Celene, sap my target.” | Selected hostile has the Sap mechanic |
| `STUN_PLAYER_TARGET` | “Celene, stun my target.” | Selected hostile enters the stunned state |
| `SLOW_FALL_ISSUER` | “Lyra, cast Slow Fall.” | Issuer has the Slow Fall aura |
| `POWER_UP` | “Power up; use your cooldowns.” | Class/spec boost strategy active |
| `START_FARMING` | “Go farm and gather.” | Grind and gather strategies active |
| `STOP_FARMING` | “Stop farming and regroup.” | Farm strategies absent and follow active |
| `START_ECONOMY` | “Start economy work.” | Persisted economy profile enabled |
| `STOP_ECONOMY` | “Stop economy work.” | Profile disabled and bot regroups |
| `WORK_AUCTION_HOUSE` | “Work the auction house.” | One owned listing or useful purchase persisted |
| `CRAFT_SUPPLIES` | “Craft something useful.” | Profession-aware craft action accepted |
| `COLLECT_MAIL` | “Collect your mail.” | Delivered-mail count decreases at a mailbox |
| `DEPOSIT_GUILD_BANK` | “Deposit your ore into the guild bank.” | Eligible gathered stacks persisted in guild-bank tab 0 |
| `SHARE_GOLD` | “Share some gold with me.” | Bounded surplus mailed to the issuer |

Common explicit wording is routed deterministically. Natural wording may also
produce one allowlisted `[INTENT: ...]` tag from the model, but only on a human
chat turn containing a request cue and language semantically compatible with
that exact intent. World events, casual observations, mismatched tags, and
unknown or multiple intent tags cannot authorize model-selected gameplay. Both
routes create the same typed queue row; neither route can submit a raw
Playerbots action. Deterministic orders do not wait on or require the persona
model.

The worldserver executor requires the bound persona bot and issuer to be online.
Orders are accepted from the bot master, party/raid leader, raid assistants,
same-guild Officers and Guild Masters, or an explicitly registered in-game
Cadia identity. Same-guild Officer authority works without a shared group, but
does not authorize `SHARE_GOLD`; guild rank alone can never take the bot's
personal gold. Bot-to-bot authorization is rejected unless that issuer is the
registered Cadia character. Expiry and selected-target validity are enforced. Targeted combat,
crowd control, and Slow Fall remain `running` until their expected game state is
observed or the verification deadline expires.

Inventory questions do not go to the persona model. The worldserver publishes a
bounded live snapshot of each controlled persona's equipped items, bag stacks,
free bag slots, and copper balance. The daemon resolves item names from the
canonical world database and renders the answer deterministically. Missing or
stale state produces an explicit refusal to guess. Persona output that claims
unverified possession, absence, quantities, equipment, or money is suppressed.

`PREPARE_PARTY` currently activates mage/priest/druid `buff` or paladin
`bkings`; it reports only that the preparation strategy is active. It does not
claim that every party buff has already landed. Mage portal, refreshment, and
Arcane Brilliance actions retain their existing spell/gameobject verification.

The researched gear, profession, addon, and economy operating plan is in
[LYRA-CELENE-OPERATIONS.md](./LYRA-CELENE-OPERATIONS.md). It distinguishes
native Playerbots behavior, the bounded character-owned economy adapter, and
the separate official realm market maker. Dialogue reports only the executor's
persisted or observed result.

### 5. Gathering profession plans (1–450)

The skill-leveling workflow below is retained for experiments but is not the
active persona mission. In the current deployment, the controlled bots' already
assigned gathering professions are provisioned to 450/450 so they can build
declared 1-450 leveling-route material kits for real players.

`daemon/config/material-kits.yaml` fixes source-backed quantities for Alchemy,
Inscription, Jewelcrafting, Engineering, and Tailoring. The local LLM orders
qualified workers inside each fixed acquisition mode; validation prevents it
from changing item entries, counts, sources, zones, guild policy, or authority.
The compiled executor compares each target with real guild-bank item instances,
deposits only actual matching stacks, and uses cumulative thresholds for
materials shared by multiple kits.

Choice-dependent tails are explicit rather than guessed by the model: Frost
Wyrm flasks (Alchemy), recurring research (Inscription), Earthsiege meta gems
(Jewelcrafting), Gnomish Army Knives (Engineering), and a 40-bag contingency
reserve (Tailoring). Guide quantities are approximate where skill-ups are
yellow or green; a completed bank target means the declared reserve is present,
not that cooldowns or probabilistic skill gains are bypassed.

```bash
.venv/bin/synthetic-daemon plan-material-kits --activate \
  --model cadia_persona --api-base http://127.0.0.1:8098/v1 \
  --profession alchemy --profession inscription \
  --profession jewelcrafting --profession engineering \
  --profession tailoring
```

New group membership does not automatically summon a persona. The bot continues
its material work and asks whether to report now or keep working. An explicit
answer becomes `REPORT_TO_GROUP` or `CONTINUE_ROUTINE`; leaving the group restores
the routine immediately. Faction-compatible taxi nodes and a target-scoped work
teleport provide route recovery without granting an account GM rank.

The local guide catalog in
`daemon/config/profession-guides.yaml` is a validated projection of the cited
WotLK 1–450 Mining, Herbalism, and Skinning guides. It fixes every skill range,
material family, conservative character-level gate, allowed zone, tool, and
guild-bank policy. The local LLM is called only when an operator creates a new
plan. It chooses one allowlisted zone for each fixed stage, one bot/profession
at a time, through a JSON schema whose zone values are literal enums. A second
validator rejects missing, duplicated, invented, or changed objectives.

From the daemon directory:

```bash
.venv/bin/synthetic-daemon init-db
.venv/bin/synthetic-daemon plan-professions --activate \
  --model cadia_persona --api-base http://127.0.0.1:8098/v1
```

Activation writes an owner/provenance record, the model plan, cited source
URLs, and deterministic stage rows. It does not add an idle model heartbeat.
The worldserver module then performs the continuing work without LLM calls:

- a bot led by a real player stays with the party and gathers nearby resources;
- an unattended online bot travels to its selected zone and enables native
  Playerbots travel, grind, loot, and gathering behavior;
- one lowest-skill profession objective runs per bot at a time, preventing two
  professions from repeatedly replacing the same travel target;
- if Playerbots has no cataloged destination for that zone, the executor builds
  a persistent native travel target from a real gatherable node or skinnable
  creature spawn in the allowlisted zone; it never teleports the bot;
- pooled ore and herb routes are refined against currently spawned nodes in the
  loaded world, and a normal non-pooled Durotar Copper Vein provides a
  reproducible skill-1 bootstrap/acceptance route;
- the next gathering rank is learned only after normal WotLK skill and
  character-level prerequisites; current skill points are never granted;
- only a mining pick or skinning knife may be provisioned as a prerequisite;
- eligible ore, stone, gems, herbs, elemental gathering reagents, leather, and
  hides are deposited promptly into guild-bank tab 0 whenever a stack appears
  and while draining remaining materials at stage completion; and
- real guild deposit rights and bank capacity are enforced, with every tool,
  rank, deposit, and stage result written to `synthetic_profession_ledger`.

Level-with-the-party bots wait at the recorded character-level gates rather
than being boosted or sent into lethal zones. Account bots must be online—such
as after being added to a player's group—for their objectives to execute.

---

## Raid behavior: Playerbots, not the LLM

`mod-playerbots` automatically applies its instance strategies when
`AiPlayerbot.ApplyInstanceStrategies = 1` (the module default). The installed
branch includes an `icc` strategy for map 631 with encounter-specific triggers
and actions for every Icecrown Citadel wing, including Marrowgar spikes and
Coldflame, Gunship cannons, Saurfang adds and tank swaps, Putricide hazards,
Valithria portals, Sindragosa mechanics, and Lich King traps and plague.

This is deterministic C++ raid AI. It is not LLM reasoning or learning, and it
does not guarantee a clear: composition, equipment, formation, pathing, server
version, and encounter-script bugs still matter. See
[PLAYERBOTS-RAID-OPERATIONS.md](../PLAYERBOTS-RAID-OPERATIONS.md) for the
operator checklist and bounded boss-recovery procedure.

---

## 🎨 Extending beyond the controlled roster

The runtime allowlist intentionally contains only Lyra, Celene, Ray, and
Browntown. Adding another persona requires an owner-directed configuration
change, a verified canonical character binding, tests, and a restart; a YAML
entry alone does not grant model or action access.

Edit `guides/wow-wotlk/synthetic-players/daemon/config/personas.yaml` or insert rows directly into `synthetic_bot_personas` in MySQL:

```yaml
personas:
  valgar:
    name: "Valgar"
    class: "Death Knight"
    race: "Undead"
    faction: "Horde"
    traits: "Cold, pragmatic, speaks of the frozen wastes and the Lich King's grip."
    style: "Low, solemn tone, minimal humor, intense battlefield focus."
    backstory: "Broken free from the Lich King's will, seeking vengeance in Icecrown."
```
