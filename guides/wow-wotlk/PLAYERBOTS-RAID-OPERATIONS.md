# Playerbots raid operations

`mod-playerbots` remains the authority for companion movement, combat, spell
selection, and encounter reactions. A persona LLM can speak about the fight,
but it does not plan or execute raid mechanics.

## Icecrown Citadel coverage

With `AiPlayerbot.ApplyInstanceStrategies = 1`, the installed module adds its
`icc` strategy automatically on map 631. The current source contains dedicated
triggers and actions for:

- Lord Marrowgar, Lady Deathwhisper, Gunship Battle, and Deathbringer Saurfang;
- Festergut, Rotface, and Professor Putricide;
- Blood Prince Council and Blood-Queen Lana'thel;
- Valithria Dreamwalker, Sindragosa, and the Lich King.

Examples include Bone Spike targeting, Coldflame avoidance, cannon and rocket-
pack use, tank swaps for Rune of Blood, ooze and plague handling, Valithria
portals, frost-beacon positioning, Shadow Traps, and Necrotic Plague movement.

Coverage means the code has a strategy; it does not mean every composition or
server revision will clear the encounter unattended. Verify roles, gear,
talents, consumables, formation, and bot strategy state. Pathfinding and
encounter-script defects can still require a reset or manual intervention.

## Before a pull

1. Confirm every intended companion is online, grouped, alive, and inside the
   same raid instance.
2. Confirm tank, healer, and damage roles rather than relying only on class.
3. Use ordinary Playerbots commands to inspect or change strategies. Do not
   route free-form LLM output to dot commands.
4. Check the encounter state with the running server's `.help instance` and
   `.instance getbossstate` commands; exact syntax varies by core revision.
5. Avoid GM instant-kill abilities when you want normal loot attribution.

## Boss recovery after an accidental GM kill

Start with the least invasive option:

```text
.respawn all
```

If trash returns but a boss does not, inspect the instance encounter state and
the boss's `creature_respawn` row. Some AzerothCore raid bosses use a self-link
in `linked_respawn`; that link intentionally blocks ordinary forced respawn and
can reschedule the creature far into the future.

The bounded recovery sequence is:

1. Identify exactly one boss spawn GUID, map, and instance. Do not use a broad
   creature-table update.
2. Save the exact `linked_respawn` row before changing anything.
3. Temporarily remove only that self-link and reload linked-respawn data.
4. Force-respawn the exact creature entry in the exact map/instance.
5. Verify the boss is present and the stale `creature_respawn` row is gone.
6. Restore the saved self-link immediately and reload linked-respawn data.
7. Recheck encounter state and worldserver health.

Database-level recovery is an administrator action. Back up first, run it from
the server console with an operator watching the result, and never leave a
self-link removed. If the encounter remains inconsistent, reset the instance
or wait for its normal reset instead of repeatedly editing broad world state.
