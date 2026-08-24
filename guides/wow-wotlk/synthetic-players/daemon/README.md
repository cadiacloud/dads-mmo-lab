# Synthetic Players Daemon

This Python service bridges AzerothCore WotLK 3.3.5a chat events to a local
OpenAI-compatible endpoint such as vLLM. It manages persona prompts, short
conversation context, persistent persona bindings, and a finite action catalog.
It does not replace `mod-playerbots` movement or combat AI.

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

`config.yaml` is local configuration and should not contain committed secrets.
The model endpoint should remain loopback- or private-network-scoped.

## Mechanical-action boundary

The model may emit only posture/emote actions and the finite mage actions
`PORTAL <DESTINATION>`, `REFRESHMENT`, and `BUFF ARCANE BRILLIANCE`. Explicit
mage requests also pass through the deterministic matcher in
`synthetic_daemon/action_intent.py`. ALE enforces live preconditions and records
execution verification separately from dialogue delivery.

For the complete setup and threat boundary, see
[HOWTO-SYNTHETIC-PLAYERS.md](../HOWTO-SYNTHETIC-PLAYERS.md).
