#!/usr/bin/env python3
"""Broadcast AzerothCore health to a Discord webhook."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


CONTAINERS = {
    "Database": "ac-database",
    "Authentication": "ac-authserver",
    "World": "ac-worldserver",
}
PORTS = {
    "Realm login": 3724,
    "SOAP": 7878,
    "World socket": 8085,
}


@dataclass(frozen=True)
class Check:
    name: str
    healthy: bool
    detail: str


def run_command(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)


def container_check(label: str, name: str) -> Check:
    result = run_command(
        "docker",
        "inspect",
        "--format",
        "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.RestartCount}}",
        name,
    )
    if result.returncode != 0:
        return Check(label, False, "missing")
    status, health, restarts = result.stdout.strip().split("|", 2)
    healthy = status == "running" and health not in {"starting", "unhealthy"}
    detail = status
    if health != "none":
        detail += f", {health}"
    if restarts != "0":
        detail += f", restarts={restarts}"
    return Check(label, healthy, detail)


def port_check(label: str, port: int, timeout: float = 1.0) -> Check:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return Check(label, True, "accepting connections")
    except OSError:
        return Check(label, False, "unreachable")


def collect_checks() -> list[Check]:
    checks = [container_check(label, name) for label, name in CONTAINERS.items()]
    checks.extend(port_check(label, port) for label, port in PORTS.items())
    return checks


def fingerprint(checks: list[Check]) -> str:
    body = json.dumps([asdict(check) for check in checks], sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


def discord_payload(checks: list[Check], *, reason: str) -> dict[str, object]:
    healthy = all(check.healthy for check in checks)
    status = "ONLINE" if healthy else "DEGRADED"
    fields = [
        {
            "name": f"{'✅' if check.healthy else '❌'} {check.name}",
            "value": check.detail,
            "inline": True,
        }
        for check in checks
    ]
    return {
        "username": "WoW Realm Health",
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": f"AzerothCore realm: {status}",
                "description": f"Health broadcast: {reason}",
                "color": 0x2ECC71 if healthy else 0xE74C3C,
                "fields": fields,
                "footer": {"text": "Private AzerothCore realm"},
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        ],
    }


def post_webhook(url: str, payload: dict[str, object]) -> None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "wow-health-bot/1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status not in {200, 204}:
                raise RuntimeError(f"Discord returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Discord returned HTTP {exc.code}") from exc


def load_state(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_state(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n")
    temporary.replace(path)


def evaluate_once(*, dry_run: bool, force: bool) -> int:
    checks = collect_checks()
    current = fingerprint(checks)
    state_path = Path(os.environ.get("WOW_HEALTH_STATE_FILE", "~/.local/state/wow-health-bot/state.json")).expanduser()
    heartbeat = int(os.environ.get("WOW_HEALTH_HEARTBEAT_SECONDS", "3600"))
    prior = load_state(state_path)
    now = int(time.time())
    changed = prior.get("fingerprint") != current
    heartbeat_due = now - int(prior.get("last_post", 0)) >= heartbeat
    reason = "startup" if not prior else "state changed" if changed else "scheduled heartbeat"

    if force or changed or heartbeat_due:
        payload = discord_payload(checks, reason=reason)
        if dry_run:
            print(json.dumps(payload, indent=2))
        else:
            webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
            if not webhook:
                print("DISCORD_WEBHOOK_URL is not configured", file=sys.stderr)
                return 2
            post_webhook(webhook, payload)
            save_state(state_path, {"fingerprint": current, "last_post": now})

    return 0 if all(check.healthy for check in checks) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="check once instead of polling")
    parser.add_argument("--dry-run", action="store_true", help="print the Discord payload without posting")
    parser.add_argument("--force", action="store_true", help="post even if state and heartbeat are unchanged")
    args = parser.parse_args()

    if args.once:
        return evaluate_once(dry_run=args.dry_run, force=args.force)

    interval = int(os.environ.get("WOW_HEALTH_POLL_SECONDS", "60"))
    while True:
        try:
            evaluate_once(dry_run=args.dry_run, force=False)
        except Exception as exc:  # keep monitoring after transient Docker/Discord failures
            print(f"health cycle failed: {exc}", file=sys.stderr, flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
