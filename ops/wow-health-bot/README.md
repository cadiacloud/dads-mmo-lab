# WoW Realm Health broadcaster

This small, dependency-free service checks the local AzerothCore Docker
containers and loopback service ports, then posts a Discord embed when health
changes and on a periodic heartbeat. It never reads database credentials,
player data, chat, or LAN addresses.

Required secret configuration:

```text
DISCORD_WEBHOOK_URL=<Discord channel webhook URL>
```

Optional settings:

```text
WOW_HEALTH_POLL_SECONDS=60
WOW_HEALTH_HEARTBEAT_SECONDS=3600
```

The deployment keeps secrets in `~/.config/wow-health-bot/env` with mode
`0600`. The tracked systemd user unit references that file but contains no
secret values.

Useful commands:

```bash
python ops/wow-health-bot/wow_health_bot.py --once --dry-run --force
systemctl --user status wow-health-bot.service
journalctl --user -u wow-health-bot.service -f
```
