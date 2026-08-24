# 🧠 Dad's MMO Lab: Synthetic Players — How-To Guide
## Autonomous Local LLM Agent Bridge for AzerothCore WoW (WotLK 3.3.5a)

Add local-LLM dialogue, personality, conversational memory, and bounded presentation actions to real AzerothCore Playerbot characters. The LLM does not replace Playerbots movement, pathfinding, combat, or tactical AI.

---

## 🏛️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    AzerothCore Server                       │
│                                                             │
│  ┌───────────────────────┐       ┌───────────────────────┐  │
│  │    mod-playerbots     │       │  SyntheticPlayers.lua │  │
│  │ (Movement, Combat AI) │       │  (ALE Event & Chat)   │  │
│  └───────────┬───────────┘       └───────────┬───────────┘  │
└──────────────┼───────────────────────────────┼──────────────┘
               │                               │
               ▼                               ▼
      [acore_characters.synthetic_inbox / synthetic_outbox]
                               ▲
                               │ Async MySQL Poller (500ms)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│               Synthetic Players Python Daemon               │
│                                                             │
│  - Persona Manager (Lore-grounded archetypes & styles)      │
│  - Conversational & Relationship Memory (Rolling buffers)   │
│  - Bounded Presentation Action Parser ([ACTION: ...])       │
└──────────────────────────────┬──────────────────────────────┘
                               │ OpenAI-Compatible API
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                vLLM Server (Local Gemma 4)                  │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚡ Key Features

1. **In-Game Whispers & Chat:** Whisper any bot or talk in Party/Say/Guild chat; the bot replies in-character based on its class, race, and background lore.
2. **Context-Aware:** Replies include the speaker, bot identity, class/race, current zone, and recent conversation context.
3. **World Event Reactions:** Grouped bots can comment on elite/boss kills, player deaths, level-ups, achievements, and targeted emotes.
4. **Bounded Actions:** A reply may make the bot emote, change posture, or ask a mage to cast one of a finite set of known portal spells. Combat strategy and arbitrary Playerbots, server, shell, or database commands are not delegated to the LLM.
5. **Low-Impact Queueing:** The database inbox/outbox decouples model latency from the world thread. Operators must still monitor database and ALE latency under load.
6. **Action Audit:** `synthetic_action_audit` records whether a bounded action was accepted or rejected independently from chat-delivery status, without duplicating the conversation text.

### Privacy and retention

This prototype processes player chat and stores queue rows plus selected memory
summaries in `acore_characters`. Its normal logs also identify the responding
bot and player. Treat the database, daemon logs, and persona bindings as private
game-session data: restrict access, define retention, and do not publish raw
conversation records. The action-audit table intentionally stores the typed
action and outcome without copying dialogue text.

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

### Step 4: Launch vLLM with Gemma 4

Start your local vLLM instance serving your Gemma 4 model:

```bash
vllm serve /path/to/your/model \
    --host 127.0.0.1 \
    --port 8000 \
    --tensor-parallel-size 1 \
    --gpu-memory-utilization 0.90 \
    --max-model-len 4096
```

### Step 5: Start the Synthetic Players Daemon

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
| Brog | Orc | Warrior | Gruff, honorable frontline veteran |
| Lyra | Blood Elf | Mage | Sarcastic arcane scholar |
| Theron | Human | Paladin | Protective knight of the Light |
| Fizwick | Gnome | Rogue | Fast-talking tinkerer and lockpicker |
| Eluneis | Night Elf | Druid | Calm Cenarion guardian |

`synthetic_persona_bindings` binds each persona name to one character GUID and records that character's original name, race, class, and gender. The daemon validates every binding at startup and rejects an event whose target GUID does not match the named persona. This prevents a prompt or forged queue record from impersonating a canonical persona.

The division of responsibility is explicit:

- The local LLM supplies dialogue, persona voice, conversational context, and typed requests from the bounded action catalog.
- `mod-playerbots` supplies movement, combat, targeting, pathfinding, spell use, loot, and normal game behavior.
- `SyntheticPlayers.lua` carries real in-game events to the daemon and delivers the generated response through the bound Playerbot object.

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
Send an in-game whisper to an online canonical persona bot:
```text
/w Brog What do you think of this dungeon?
```
**Brog replies:**
> *"The stone is old and reeking of Scourge filth. Keep your blade sharp and stay behind my shield."*

### 2. Party & Group Banter
In party chat with at least one online Playerbot, use `@Name` to choose a specific persona. Without a mention, the first Playerbot in the group receives the event:
```text
/p @Lyra, do you have extra water before we pull the boss?
```
**Lyra replies:**
> *"Of course. Give me a moment and I’ll set the table for everyone."*

### 3. Bounded Actions
```text
/w Brog Sit down and take a quick break.
```
**Brog:**
> *"Agreed. Catching my breath before the next charge."* *(Brog sits down in-game)*

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

## 🎨 Customizing Bot Personas

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
