"""Deterministic, worldserver-grounded inventory replies."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional


_INVENTORY_QUERY = re.compile(
    r"\b(?:what|which)\b.*\b(?:do you have|are you carrying|inventory|bags?|materials?|mats?|gear|equipment)\b|"
    r"\bhow\s+(?:much|many)\b.*\b(?:do you have|are you carrying|in your bags?|gold)\b|"
    r"\bdo you have\b.*(?:\?|$)|"
    r"\b(?:show|check|list)\b.*\b(?:inventory|bags?|materials?|mats?|gear|equipment)\b|"
    r"\b(?:inventory|bags?|materials?|mats?|gear|equipment|gold)\s*\?\s*$|"
    r"\b(?:copper|ore|herbs?|leather|hides?|gems?|stone|crystals?|silk)\s*\?\s*$",
    re.IGNORECASE,
)

_MATERIAL_TOPIC = re.compile(
    r"\b(?:materials?|mats?|ore|herbs?|leather|hides?|gems?|stone|crystals?|silk)\b",
    re.IGNORECASE,
)

_INVENTORY_CLAIM = re.compile(
    r"\b(?:i\s+have|i've\s+got|i\s+carry|i'm\s+carrying|my\s+(?:bags?|inventory|stash)|"
    r"stockpil(?:e|ed|ing)|saved\s+up|tucked\s+away)\b",
    re.IGNORECASE,
)

_INVENTORY_OBJECT = re.compile(
    r"\b(?:gold|silver|copper|ore|herbs?|materials?|mats?|items?|gear|weapons?|armor|"
    r"potions?|food|water|silk|cloth|crystals?|gems?|leather|hides?|reagents?|supplies|"
    r"stacks?|bags?|inventory|stash)\b",
    re.IGNORECASE,
)


def is_inventory_query(message: str) -> bool:
    """Identify questions that require authoritative character inventory state."""
    return bool(_INVENTORY_QUERY.search(message.strip()))


def contains_unverified_inventory_claim(message: str) -> bool:
    """Reject model-authored ownership claims not produced by the state renderer."""
    return bool(_INVENTORY_CLAIM.search(message) and _INVENTORY_OBJECT.search(message))


def _money_text(copper: int) -> str:
    gold, remainder = divmod(max(0, copper), 10_000)
    silver, copper = divmod(remainder, 100)
    return f"{gold}g {silver}s {copper}c"


def _bounded_item_list(prefix: str, items: Iterable[Dict[str, Any]], suffix: str = "") -> str:
    """Render exact item counts within the practical 3.3.5 chat-message budget."""
    rendered: List[str] = []
    omitted = 0
    base_length = len(prefix) + len(suffix)
    for item in items:
        label = f"{item['name']} x{int(item['count'])}"
        candidate = ", ".join([*rendered, label])
        if base_length + len(candidate) <= 215:
            rendered.append(label)
        else:
            omitted += 1

    body = ", ".join(rendered) if rendered else "none"
    if omitted:
        body += f", plus {omitted} other item type{'s' if omitted != 1 else ''}"
    return f"{prefix}{body}{suffix}"


def _requested_term(message: str) -> Optional[str]:
    normalized = " ".join(message.strip().rstrip("?").split())
    patterns = (
        r"\bhow\s+(?:much|many)\s+(.+?)\s+do\s+you\s+have\b",
        r"\bdo\s+you\s+have\s+(?:any\s+)?(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            term = match.group(1).strip(" .,!?")
            if term and term.casefold() not in {"items", "anything", "materials", "mats"}:
                return term
    return None


def render_inventory_response(
    bot_name: str,
    message: str,
    snapshot: Optional[Dict[str, Any]],
    max_age_seconds: int = 5,
) -> str:
    """Answer only from a fresh authoritative projection; never infer contents."""
    if not snapshot or int(snapshot.get("age_seconds", max_age_seconds + 1)) > max_age_seconds:
        return "I can't verify my live inventory right now, so I won't guess."

    lowered = message.casefold()
    if "gold" in lowered or "money" in lowered:
        return f"Verified money: {_money_text(int(snapshot.get('money_copper') or 0))}."

    if re.search(r"\b(?:gear|equipment|wearing|equipped)\b", lowered):
        return _bounded_item_list("Verified equipment: ", snapshot.get("equipment") or [], ".")

    items = list(snapshot.get("bags") or [])
    requested = _requested_term(message)
    if requested:
        requested_tokens = {
            token for token in re.findall(r"[a-z0-9]+", requested.casefold())
            if token not in {"any", "some", "the", "your"}
        }
        matches = []
        for item in items:
            name_tokens = set(re.findall(r"[a-z0-9]+", str(item["name"]).casefold()))
            if requested.casefold() in str(item["name"]).casefold() or (
                requested_tokens and requested_tokens.issubset(name_tokens)
            ):
                matches.append(item)
        if not matches:
            return f"Verified bags: no item matching '{requested}'."
        return _bounded_item_list(f"Verified '{requested}': ", matches, ".")

    if _MATERIAL_TOPIC.search(message):
        materials = [item for item in items if int(item.get("class") or 0) == 7]
        return _bounded_item_list("Verified trade-good materials: ", materials, ".")

    free_slots = int(snapshot.get("free_bag_slots") or 0)
    return _bounded_item_list("Verified bags: ", items, f". Free slots: {free_slots}.")
