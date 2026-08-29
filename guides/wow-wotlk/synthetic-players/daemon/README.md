# Synthetic Players Daemon

This Python service bridges AzerothCore WotLK 3.3.5a chat events to a local
OpenAI-compatible endpoint such as vLLM. It manages persona prompts, short
conversation context, persistent persona bindings, and a finite action catalog.
It does not replace `mod-playerbots` movement or combat AI.

The optional director path adds a typed goal layer. The model or deterministic
router chooses one high-level intent; `mod-cadia-player-director` authorizes it
inside worldserver and delegates execution to existing Playerbots strategies.
The daemon waits for a terminal executor result and renders that outcome from a
fixed result-code map, so a model cannot narrate an unverified success.

## Install and test

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
cp config/config.yaml.example config.yaml
synthetic-daemon health -c config.yaml
pytest
```

Initialize the queue schema and run the worker:

```bash
synthetic-daemon init-db -c config.yaml
synthetic-daemon run -c config.yaml
```

Install the worldserver executor source before rebuilding AzerothCore:

```bash
../install-player-director.sh --server-root /absolute/path/to/azerothcore
```

`config.yaml` is local configuration and should not contain committed secrets.
The model endpoint should remain loopback- or private-network-scoped.

## Mechanical-action boundary

The model may emit only posture/emote actions and the finite mage actions
`PORTAL <DESTINATION>`, `REFRESHMENT`, and `BUFF ARCANE BRILLIANCE`. Explicit
mage requests also pass through the deterministic matcher in
`synthetic_daemon/action_intent.py`. ALE enforces live preconditions and records
execution verification separately from dialogue delivery.

The director accepts movement and selected-target combat plus
`POLYMORPH_PLAYER_TARGET`, `SAP_PLAYER_TARGET`, `STUN_PLAYER_TARGET`,
`SLOW_FALL_ISSUER`, `POWER_UP`, `START_FARMING`, and `STOP_FARMING`.
The bounded economy catalog adds `START_ECONOMY`, `STOP_ECONOMY`,
`WORK_AUCTION_HOUSE`, `CRAFT_SUPPLIES`, `COLLECT_MAIL`,
`DEPOSIT_GUILD_BANK`, and `SHARE_GOLD`.
Group-duty decisions add `REPORT_TO_GROUP` and `CONTINUE_ROUTINE`. A newly
grouped persona keeps its current routine and asks its human master which mode
to use; accepting an invitation is not consent to teleport or abandon work.
Common explicit orders use deterministic routing; the model
may select the same finite intents for natural wording. The executor never
accepts model-generated raw Playerbots commands, action names, spell IDs, SQL,
GM commands, or shell commands.

Inventory and money are authoritative game state, not persona memory. The
worldserver snapshots each controlled persona's bags, equipment, free slots,
and exact copper balance into `synthetic_bot_inventory`. Inventory questions
bypass the LLM and receive a deterministic answer from a fresh snapshot; stale
or unavailable state is reported honestly. A general persona response that
still makes an unverified inventory claim is blocked before delivery.

The executor accepts commands from the bot's group master, party/raid leader,
raid assistant, a same-guild Officer or Guild Master, or the explicitly
registered Cadia identity. Guild rank does not, by itself, authorize
`SHARE_GOLD`.

For the complete setup and threat boundary, see
[HOWTO-SYNTHETIC-PLAYERS.md](../HOWTO-SYNTHETIC-PLAYERS.md).
The persona-specific build and economy policy is in
[LYRA-CELENE-OPERATIONS.md](../LYRA-CELENE-OPERATIONS.md).

## Profession objective planner

The one-shot planner uses `config/profession-guides.yaml` and accepts live
learned gathering professions only from the controlled persona roster. It asks
the local model to select among guide-derived zone enums, validates the model
document again, records authorization and source provenance, and expands the
result into fixed 1–450 stage objectives:

```bash
synthetic-daemon plan-professions --activate \
  --model cadia_persona --api-base http://127.0.0.1:8098/v1
```

`--activate` is mandatory because this command writes live objectives. The LLM
does not remain in the execution loop. Travel, gathering, rank gates, tool
checks, guild permissions, deposits, and audit records are enforced by the
compiled worldserver module. The executor runs one lowest-skill profession per
bot at a time and deposits each eligible gathered stack promptly into the
configured guild-bank tab.
An authorized leader can also request an immediate full drain with “deposit
your ore into the guild bank”; the executor reports only the persisted outcome.

## Real-player material kits

The active workflow does not level the persona bots' professions. The compiled
executor maxes only each persona's already-learned gathering professions and
grants faction-compatible taxi nodes. It does not replace professions or grant a
GM rank. `config/material-kits.yaml` fixes source-backed quantities for Alchemy,
Inscription, Jewelcrafting, Engineering, and Tailoring 1–450. The local LLM may
only order qualified bots within each acquisition mode; it cannot change item
names, counts, sources, zones, inventory totals, or guild policy.

```bash
synthetic-daemon plan-material-kits --activate \
  --model cadia_persona --api-base http://127.0.0.1:8098/v1 \
  --profession alchemy --profession inscription \
  --profession jewelcrafting --profession engineering \
  --profession tailoring
```

The executor compares each target with actual guild-bank item instances,
deposits the character's real matching stacks, and records progress in
`synthetic_material_kit_targets` and `synthetic_material_kit_ledger`. Shared
materials use cumulative bank thresholds so one stack cannot satisfy two kits.
`auction` targets (Arcane Dust, Infinite Dust, and the Alchemy route's Pygmy
Suckerfish) remain visibly `auction_procurement_required`; they are never
reported as gathered.

The catalog declares its choice-dependent finishes: Flask of the Frost Wyrm
for Alchemy, Earthsiege meta gems for Jewelcrafting, Gnomish Army Knives for
Engineering, recurring Northrend Inscription Research, and a conservative
40-Frostweave-Bag reserve for Tailoring. These are real leveling routes, but
yellow/green skill-up RNG and daily research can require time or a refill. The
executor reports bank coverage, not a false guarantee that a probabilistic
craft sequence has already awarded 450 skill.
