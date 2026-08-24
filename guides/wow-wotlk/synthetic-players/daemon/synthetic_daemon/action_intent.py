"""Deterministic routing for explicit, bounded in-game capability requests."""

from __future__ import annotations

import re
from typing import Optional


MAGE_CLASS_ID = 8

PORTAL_DESTINATIONS = {
    "STORMWIND": "STORMWIND",
    "IRONFORGE": "IRONFORGE",
    "DARNASSUS": "DARNASSUS",
    "EXODAR": "EXODAR",
    "THERAMORE": "THERAMORE",
    "ORGRIMMAR": "ORGRIMMAR",
    "UNDERCITY": "UNDERCITY",
    "UNDER CITY": "UNDERCITY",
    "THUNDER BLUFF": "THUNDER BLUFF",
    "THUNDERBLUFF": "THUNDER BLUFF",
    "SILVERMOON": "SILVERMOON",
    "SILVER MOON": "SILVERMOON",
    "STONARD": "STONARD",
    "SHATTRATH": "SHATTRATH",
    "DALARAN": "DALARAN",
}

_REQUEST_CUE = re.compile(
    r"\b(?:can|could|would|will)\s+you\b|\bplease\b|\b(?:give|make|conjure|create|"
    r"open|cast|drop|put|need|want|buff)\b|\bdo\s+you\s+have\b|\bhave\s+any\b",
    re.IGNORECASE,
)


def detect_explicit_action(message: str, class_id: int) -> Optional[str]:
    """Return one allowlisted action for a clear player request.

    The LLM still supplies persona dialogue, but explicit mechanical requests do
    not depend on the model remembering an action tag.
    """
    if class_id != MAGE_CLASS_ID:
        return None

    normalized = " ".join(message.upper().replace("@", " ").split())
    if not _REQUEST_CUE.search(message):
        return None

    if re.search(r"\b(?:PORTAL|TELEPORT)\b", normalized):
        for alias in sorted(PORTAL_DESTINATIONS, key=len, reverse=True):
            if re.search(rf"\b{re.escape(alias)}\b", normalized):
                return f"PORTAL {PORTAL_DESTINATIONS[alias]}"

    if re.search(r"\b(?:FOOD|WATER|REFRESHMENTS?|STRUDEL|MAGE TABLE)\b", normalized):
        return "REFRESHMENT"

    if re.search(r"\b(?:BUFF|BUFFS|INTELLECT|ARCANE BRILLIANCE|DALARAN BRILLIANCE)\b", normalized):
        return "BUFF ARCANE BRILLIANCE"

    return None


def capability_prompt_hint(action: str) -> str:
    """Tell the persona model how to speak while execution remains pending."""
    return (
        f"[Capability routing: this explicit request maps to the bounded action {action}. "
        "Respond warmly as you begin the attempt, but do not claim that it already succeeded.]"
    )
