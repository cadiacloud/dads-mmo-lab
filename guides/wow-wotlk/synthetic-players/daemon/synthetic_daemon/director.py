"""Typed high-level intents for directing Playerbots without piloting them."""

from __future__ import annotations

from enum import Enum, IntEnum
import re
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """Finite intent catalog accepted by the trusted worldserver adapter."""

    FOLLOW = "FOLLOW"
    HOLD_POSITION = "HOLD_POSITION"
    ATTACK_PLAYER_TARGET = "ATTACK_PLAYER_TARGET"
    PULL_PLAYER_TARGET = "PULL_PLAYER_TARGET"
    RETREAT = "RETREAT"
    PREPARE_PARTY = "PREPARE_PARTY"
    POLYMORPH_PLAYER_TARGET = "POLYMORPH_PLAYER_TARGET"
    SAP_PLAYER_TARGET = "SAP_PLAYER_TARGET"
    STUN_PLAYER_TARGET = "STUN_PLAYER_TARGET"
    SLOW_FALL_ISSUER = "SLOW_FALL_ISSUER"
    POWER_UP = "POWER_UP"
    START_FARMING = "START_FARMING"
    STOP_FARMING = "STOP_FARMING"
    START_ECONOMY = "START_ECONOMY"
    STOP_ECONOMY = "STOP_ECONOMY"
    WORK_AUCTION_HOUSE = "WORK_AUCTION_HOUSE"
    CRAFT_SUPPLIES = "CRAFT_SUPPLIES"
    COLLECT_MAIL = "COLLECT_MAIL"
    DEPOSIT_GUILD_BANK = "DEPOSIT_GUILD_BANK"
    SHARE_GOLD = "SHARE_GOLD"
    REPORT_TO_GROUP = "REPORT_TO_GROUP"
    CONTINUE_ROUTINE = "CONTINUE_ROUTINE"


class IntentStatus(IntEnum):
    """Lifecycle shared by the Python daemon, schema, and C++ executor."""

    PENDING = 0
    ACCEPTED = 1
    RUNNING = 2
    SUCCEEDED = 3
    FAILED = 4
    REJECTED = 5
    EXPIRED = 6
    PREEMPTED = 7


TERMINAL_INTENT_STATUSES = {
    IntentStatus.SUCCEEDED,
    IntentStatus.FAILED,
    IntentStatus.REJECTED,
    IntentStatus.EXPIRED,
    IntentStatus.PREEMPTED,
}


class DirectorIntent(BaseModel):
    """Validated request written to the intent queue."""

    intent_type: IntentType
    parameters: Dict[str, Any] = Field(default_factory=dict)
    expires_in_seconds: int = Field(default=30, ge=5, le=120)


_REQUEST_CUE = re.compile(
    r"\b(?:can|could|would|will)\s+(?:you|someone|anyone)\b|\bplease\b|"
    r"\bwould\s+you\s+mind\b|\bi\s+need\s+you\s+to\b|\blet(?:'|’)s\b|"
    r"\b(?:we|you)\s+should\b",
    re.IGNORECASE,
)

_IMPERATIVE_CUE = re.compile(
    r"^\s*(?:@[A-Za-z][A-Za-z0-9]*\s+|[A-Za-z][A-Za-z0-9]*,\s*|"
    r"(?:everyone|team|party)[,:]?\s+)?(?:please\s+)?(?:follow|come|stay|hold|wait|"
    r"attack|engage|focus|kill|pull|bring|retreat|fallback|fall\s+back|flee|prepare|"
    r"ready|buff|get\s+ready|sheep|polymorph|sap|stun|slow\s+fall|power\s+up|burst|"
    r"farm|go\s+farm|harvest|gather|stop\s+farming|start\s+(?:economy|economic)\s+work|"
    r"work\s+the\s+auction\s+house|use\s+the\s+auction\s+house|list|auction|buy\s+(?:crafting\s+)?supplies|"
    r"craft|make\s+supplies|collect\s+(?:your\s+)?mail|check\s+(?:your\s+)?mail|share\s+(?:some\s+)?gold|"
    r"send\s+(?:me\s+)?(?:some\s+)?gold|put|deposit|report\s+to|join\s+us|"
    r"keep\s+working|continue\s+(?:your\s+)?(?:work|routine)|finish\s+what\s+you(?:'|’)re\s+doing|"
    r"stop\s+(?:economy|economic)\s+work)\b",
    re.IGNORECASE,
)


def has_direction_request_cue(message: str) -> bool:
    """Require evidence that a human chat turn is asking for direction."""
    return bool(_REQUEST_CUE.search(message) or _IMPERATIVE_CUE.search(message))


_INTENT_LANGUAGE = {
    IntentType.REPORT_TO_GROUP: re.compile(
        r"\b(?:report\s+to\s+(?:me|us|the\s+group)|come\s+(?:to\s+me\s+)?now|"
        r"join\s+us\s+now|come\s+join\s+(?:me|us)|stop\s+working\s+and\s+come)\b",
        re.IGNORECASE,
    ),
    IntentType.CONTINUE_ROUTINE: re.compile(
        r"\b(?:keep\s+working|continue\s+(?:your\s+)?(?:work|routine)|"
        r"finish\s+what\s+you(?:'|’)re\s+doing|take\s+your\s+time|stay\s+on\s+(?:your\s+)?task)\b",
        re.IGNORECASE,
    ),
    IntentType.FOLLOW: re.compile(
        r"\b(?:follow|com(?:e|ing)\s+with|come\s+along|stick\s+with|stay\s+with|regroup|group\s+up)\b",
        re.IGNORECASE,
    ),
    IntentType.HOLD_POSITION: re.compile(
        r"\b(?:hold|stay\s+here|wait\s+here|do\s+not\s+move|don't\s+move|position)\b",
        re.IGNORECASE,
    ),
    IntentType.ATTACK_PLAYER_TARGET: re.compile(
        r"^(?=.*\b(?:attack|engage|focus|kill|take\s+out|deal\s+with)\b)"
        r"(?=.*\b(?:my\s+target|target|this|that|it)\b).*$",
        re.IGNORECASE,
    ),
    IntentType.PULL_PLAYER_TARGET: re.compile(
        r"^(?=.*\b(?:pull|lure|bring)\b)"
        r"(?=.*\b(?:my\s+target|target|this|that|it|mob|enemy)\b).*$",
        re.IGNORECASE,
    ),
    IntentType.RETREAT: re.compile(
        r"\b(?:retreat|fallback|fall\s+back|flee|back\s+off|disengage|get\s+out)\b",
        re.IGNORECASE,
    ),
    IntentType.PREPARE_PARTY: re.compile(
        r"\b(?:prepare|ready|buff|blessing|fortitude|intellect|mark\s+of\s+the\s+wild)\b",
        re.IGNORECASE,
    ),
    IntentType.POLYMORPH_PLAYER_TARGET: re.compile(
        r"^(?=.*\b(?:sheep|polymorph)\b)(?=.*\b(?:my\s+target|target|this|that|it|mob|enemy)\b).*$",
        re.IGNORECASE,
    ),
    IntentType.SAP_PLAYER_TARGET: re.compile(
        r"^(?=.*\bsap\b)(?=.*\b(?:my\s+target|target|this|that|it|mob|enemy)\b).*$",
        re.IGNORECASE,
    ),
    IntentType.STUN_PLAYER_TARGET: re.compile(
        r"^(?=.*\bstun\b)(?=.*\b(?:my\s+target|target|this|that|it|mob|enemy)\b).*$",
        re.IGNORECASE,
    ),
    IntentType.SLOW_FALL_ISSUER: re.compile(r"\bslow\s+fall\b", re.IGNORECASE),
    IntentType.POWER_UP: re.compile(
        r"\b(?:power\s+up|burst(?:\s+mode)?|use\s+(?:your\s+)?cooldowns?|go\s+all\s+out)\b",
        re.IGNORECASE,
    ),
    IntentType.START_FARMING: re.compile(
        r"\b(?:start\s+farming|go\s+farm|farm|harvest|gather)\b",
        re.IGNORECASE,
    ),
    IntentType.STOP_FARMING: re.compile(
        r"\b(?:stop\s+farming|stop\s+gathering|finish\s+farming|quit\s+farming)\b",
        re.IGNORECASE,
    ),
    IntentType.START_ECONOMY: re.compile(
        r"\b(?:start|begin|enable)\s+(?:economy|economic|market)\s+(?:work|mode|contribution)\b|"
        r"\bcontribute\s+to\s+the\s+economy\b",
        re.IGNORECASE,
    ),
    IntentType.STOP_ECONOMY: re.compile(
        r"\b(?:stop|end|disable)\s+(?:economy|economic|market)\s+(?:work|mode|contribution)\b|"
        r"\bstop\s+contributing\s+to\s+the\s+economy\b",
        re.IGNORECASE,
    ),
    IntentType.WORK_AUCTION_HOUSE: re.compile(
        r"\b(?:work|use|check)\s+(?:at\s+)?the\s+auction\s+house\b|"
        r"\b(?:list|auction|sell)\s+(?:your\s+)?(?:extra\s+|spare\s+)?(?:items|materials|goods|loot)\b|"
        r"\bbuy\s+(?:useful\s+|needed\s+|crafting\s+)?(?:items|materials|supplies|goods)\b",
        re.IGNORECASE,
    ),
    IntentType.CRAFT_SUPPLIES: re.compile(
        r"\b(?:craft|make|produce)\s+(?:something\s+)?(?:useful|supplies|goods|materials|items)\b|"
        r"\bwork\s+on\s+(?:your\s+)?professions?\b",
        re.IGNORECASE,
    ),
    IntentType.COLLECT_MAIL: re.compile(
        r"\b(?:collect|check|open|take)\s+(?:your\s+)?mail\b|\bcheck\s+(?:your\s+)?mailbox\b",
        re.IGNORECASE,
    ),
    IntentType.DEPOSIT_GUILD_BANK: re.compile(
        r"\b(?:deposit|put|stash|bank)\b.*\b(?:guild\s+bank|guildbank)\b",
        re.IGNORECASE,
    ),
    IntentType.SHARE_GOLD: re.compile(
        r"\b(?:share|send|give|mail)\s+(?:me\s+|us\s+|the\s+group\s+)?(?:some\s+)?gold\b",
        re.IGNORECASE,
    ),
}


def message_supports_intent(message: str, intent_type: IntentType) -> bool:
    """Ensure a model-selected intent is semantically present in the request."""
    return has_direction_request_cue(message) and bool(_INTENT_LANGUAGE[intent_type].search(message))


def detect_explicit_intent(message: str) -> Optional[IntentType]:
    """Map a clear player request to one typed high-level intent.

    Deterministic routing makes common commands reliable. The model can still
    select an intent for natural wording that does not match this conservative
    catalog.
    """
    if not has_direction_request_cue(message):
        return None

    normalized = " ".join(message.upper().replace("@", " ").split())

    if re.search(
        r"\b(?:REPORT TO (?:ME|US|THE GROUP)|COME (?:TO ME )?NOW|JOIN US NOW|"
        r"COME JOIN (?:ME|US)|STOP WORKING AND COME)\b",
        normalized,
    ):
        return IntentType.REPORT_TO_GROUP

    if re.search(
        r"\b(?:KEEP WORKING|CONTINUE (?:YOUR )?(?:WORK|ROUTINE)|"
        r"FINISH WHAT YOU(?:'|’)RE DOING|TAKE YOUR TIME|STAY ON (?:YOUR )?TASK)\b",
        normalized,
    ):
        return IntentType.CONTINUE_ROUTINE

    if re.search(r"\b(?:STOP FARMING|STOP GATHERING|FINISH FARMING|QUIT FARMING)\b", normalized):
        return IntentType.STOP_FARMING

    if re.search(
        r"\b(?:STOP|END|DISABLE) (?:ECONOMY|ECONOMIC|MARKET) (?:WORK|MODE|CONTRIBUTION)\b|"
        r"\bSTOP CONTRIBUTING TO THE ECONOMY\b",
        normalized,
    ):
        return IntentType.STOP_ECONOMY

    if re.search(r"\b(?:COLLECT|CHECK|OPEN|TAKE) (?:YOUR )?MAIL\b|\bCHECK (?:YOUR )?MAILBOX\b", normalized):
        return IntentType.COLLECT_MAIL

    if re.search(r"\b(?:DEPOSIT|PUT|STASH|BANK)\b.*\b(?:GUILD BANK|GUILDBANK)\b", normalized):
        return IntentType.DEPOSIT_GUILD_BANK

    if re.search(
        r"\b(?:SHARE|SEND|GIVE|MAIL) (?:ME |US |THE GROUP )?(?:SOME )?GOLD\b",
        normalized,
    ):
        return IntentType.SHARE_GOLD

    if re.search(
        r"\b(?:WORK|USE|CHECK) (?:AT )?THE AUCTION HOUSE\b|"
        r"\b(?:LIST|AUCTION|SELL) (?:YOUR )?(?:EXTRA |SPARE )?(?:ITEMS|MATERIALS|GOODS|LOOT)\b|"
        r"\bBUY (?:USEFUL |NEEDED |CRAFTING )?(?:ITEMS|MATERIALS|SUPPLIES|GOODS)\b",
        normalized,
    ):
        return IntentType.WORK_AUCTION_HOUSE

    if re.search(
        r"\b(?:CRAFT|MAKE|PRODUCE) (?:SOMETHING )?(?:USEFUL|SUPPLIES|GOODS|MATERIALS|ITEMS)\b|"
        r"\bWORK ON (?:YOUR )?PROFESSIONS?\b",
        normalized,
    ):
        return IntentType.CRAFT_SUPPLIES

    if re.search(
        r"\b(?:START|BEGIN|ENABLE) (?:ECONOMY|ECONOMIC|MARKET) (?:WORK|MODE|CONTRIBUTION)\b|"
        r"\bCONTRIBUTE TO THE ECONOMY\b",
        normalized,
    ):
        return IntentType.START_ECONOMY

    if re.search(r"\b(?:SHEEP|POLYMORPH)\b", normalized) and re.search(
        r"\b(?:MY TARGET|TARGET|THIS|THAT|IT|MOB|ENEMY)\b",
        normalized,
    ):
        return IntentType.POLYMORPH_PLAYER_TARGET

    if re.search(r"\bSAP\b", normalized) and re.search(
        r"\b(?:MY TARGET|TARGET|THIS|THAT|IT|MOB|ENEMY)\b",
        normalized,
    ):
        return IntentType.SAP_PLAYER_TARGET

    if re.search(r"\bSTUN\b", normalized) and re.search(
        r"\b(?:MY TARGET|TARGET|THIS|THAT|IT|MOB|ENEMY)\b",
        normalized,
    ):
        return IntentType.STUN_PLAYER_TARGET

    if re.search(r"\bSLOW FALL\b", normalized):
        return IntentType.SLOW_FALL_ISSUER

    if re.search(r"\b(?:POWER UP|BURST(?: MODE)?|USE (?:YOUR )?COOLDOWNS?|GO ALL OUT)\b", normalized):
        return IntentType.POWER_UP

    if re.search(r"\b(?:START FARMING|GO FARM|FARM|HARVEST|GATHER)\b", normalized):
        return IntentType.START_FARMING

    if re.search(r"\b(?:RETREAT|FLEE|FALL BACK|FALLBACK|BACK OFF)\b", normalized):
        return IntentType.RETREAT

    if re.search(r"\b(?:HOLD (?:THIS )?POSITION|STAY HERE|WAIT HERE|DON'T MOVE|DO NOT MOVE)\b", normalized):
        return IntentType.HOLD_POSITION

    if re.search(r"\b(?:PULL|BRING)\b", normalized) and re.search(
        r"\b(?:TARGET|MOB|ENEMY|THIS|IT)\b",
        normalized,
    ):
        return IntentType.PULL_PLAYER_TARGET

    if re.search(r"\b(?:ATTACK|ENGAGE|FOCUS|KILL)\b", normalized) and re.search(
        r"\b(?:MY TARGET|TARGET|THIS|IT)\b",
        normalized,
    ):
        return IntentType.ATTACK_PLAYER_TARGET

    if re.search(r"\b(?:FOLLOW ME|COME WITH ME|COME ALONG|REGROUP|GROUP UP)\b", normalized):
        return IntentType.FOLLOW

    if re.search(r"\b(?:PREPARE|GET READY|READY UP|BUFF UP|BUFF THE PARTY|BUFF US)\b", normalized):
        return IntentType.PREPARE_PARTY

    return None


def format_state_for_prompt(state: Optional[Dict[str, Any]]) -> str:
    """Render a bounded server snapshot without exposing internal free-form values."""
    if not state:
        return "Playerbot state snapshot: unavailable (do not assume game state)."

    target_guid = int(state.get("target_guid") or 0)
    return (
        "Playerbot state snapshot: "
        f"health={int(state.get('health_pct') or 0)}%, "
        f"power={int(state.get('power_pct') or 0)}%, "
        f"combat={bool(state.get('in_combat'))}, "
        f"dead={bool(state.get('is_dead'))}, "
        f"map={int(state.get('map_id') or 0)}, "
        f"zone={int(state.get('zone_id') or 0)}, "
        f"target_guid={target_guid}, "
        f"follow={bool(state.get('follow_active'))}, "
        f"hold={bool(state.get('stay_active'))}, "
        f"passive={bool(state.get('passive_active'))}, "
        f"prepare={bool(state.get('prepare_active'))}."
    )


def fallback_result_message(intent_type: str, status: int, result_code: str) -> str:
    """Render a truthful terminal result without asking a model to interpret it."""
    success = status == IntentStatus.SUCCEEDED
    if success:
        return {
            (IntentType.FOLLOW.value, "follow_strategy_active"): "Following.",
            (IntentType.HOLD_POSITION.value, "hold_strategy_active"): "Holding this position.",
            (IntentType.RETREAT.value, "retreat_strategy_active"): "Falling back now.",
            (IntentType.PREPARE_PARTY.value, "prepare_strategy_active"): "I'm preparing now.",
            (IntentType.ATTACK_PLAYER_TARGET.value, "attack_engaged"): "I've engaged your target.",
            (IntentType.ATTACK_PLAYER_TARGET.value, "attack_target_defeated"): "Your target is down.",
            (IntentType.PULL_PLAYER_TARGET.value, "pull_engaged"): "The pull is underway.",
            (IntentType.PULL_PLAYER_TARGET.value, "pull_target_defeated"): "The pull target is down.",
            (IntentType.POLYMORPH_PLAYER_TARGET.value, "target_polymorphed"): "Your target is sheeped.",
            (IntentType.SAP_PLAYER_TARGET.value, "target_sapped"): "Your target is sapped.",
            (IntentType.STUN_PLAYER_TARGET.value, "target_stunned"): "Your target is stunned.",
            (IntentType.SLOW_FALL_ISSUER.value, "slow_fall_active"): "Slow Fall is active on you.",
            (IntentType.POWER_UP.value, "boost_strategy_active"): "Burst mode is active.",
            (IntentType.START_FARMING.value, "farming_strategy_active"): "I'm gathering and farming nearby.",
            (IntentType.STOP_FARMING.value, "farming_strategy_stopped"): "Farming is stopped; I'm regrouping.",
            (IntentType.START_ECONOMY.value, "economy_enabled"): "Economy work is active. I'll gather, craft, and trade when the group does not need me.",
            (IntentType.STOP_ECONOMY.value, "economy_disabled"): "Economy work is stopped; I'm regrouping.",
            (IntentType.WORK_AUCTION_HOUSE.value, "auction_listed"): "I listed useful surplus from my own inventory.",
            (IntentType.WORK_AUCTION_HOUSE.value, "auction_bought"): "I bought a useful supply lot with my own gold; delivery is in my mailbox.",
            (IntentType.WORK_AUCTION_HOUSE.value, "auction_no_work"): "I checked the market, but found nothing responsible to list or buy.",
            (IntentType.CRAFT_SUPPLIES.value, "craft_started"): "I'm crafting from the materials I actually have.",
            (IntentType.COLLECT_MAIL.value, "mail_collected"): "I collected the delivered mail.",
            (IntentType.DEPOSIT_GUILD_BANK.value, "guild_bank_deposited"): "I deposited every eligible gathered stack from my bags into the first guild-bank tab.",
            (IntentType.DEPOSIT_GUILD_BANK.value, "guild_bank_nothing_to_deposit"): "I checked my bags; I don't have eligible ore, herbs, or hides to deposit.",
            (IntentType.DEPOSIT_GUILD_BANK.value, "guild_bank_deposit_partial"): "I deposited what would fit, but the guild bank filled up.",
            (IntentType.SHARE_GOLD.value, "gold_shared"): "I mailed you a bounded share of my surplus gold.",
            (IntentType.REPORT_TO_GROUP.value, "reported_to_group"): "On my way. I'm reporting to the group now.",
            (IntentType.CONTINUE_ROUTINE.value, "routine_continuing"): "I'll keep working on the material kits. Call me when you need me.",
        }.get((intent_type, result_code), "I couldn't verify that order's result.")

    return {
        "not_grouped": "Group with me first, then ask again.",
        "not_grouped_or_guild_officer": "Group with me, or issue that order as an Officer or Guild Master in my guild.",
        "authority_denied": "I can't take that order from you.",
        "issuer_not_bot_master": "My current leader needs to give that order.",
        "wrong_class": "That order does not match my class abilities.",
        "spell_not_known": "I have not learned that ability yet.",
        "spell_not_ready": "I cannot use that ability on the target right now.",
        "bot_dead": "I can't do that while I'm dead.",
        "in_combat": "I can't prepare that while we're fighting.",
        "not_in_same_group": "Invite me to your group first, then ask whether I should report or keep working.",
        "report_teleport_failed": "I accepted the report order, but could not reach the group safely.",
        "no_player_target": "Select a target for me first.",
        "target_not_hostile": "That isn't a valid hostile target.",
        "target_unavailable": "I lost track of that target before I could verify the order.",
        "prepare_strategy_unavailable": "I don't have a preparation routine for that yet.",
        "economy_busy_with_group": "I'll handle economy work after the group no longer needs me.",
        "economy_no_surplus": "I don't have responsible surplus to list right now.",
        "economy_no_purchase": "I found no useful purchase within my reserve and spending limits.",
        "craft_unavailable": "I don't have a useful recipe and the required materials ready.",
        "mailbox_not_nearby": "Bring me near a mailbox and ask again.",
        "no_delivered_mail": "I don't have delivered mail to collect.",
        "profession_objective_missing": "I don't have an active gathering plan that defines safe guild-bank materials.",
        "guild_bank_unavailable": "I'm not in a guild with an available guild bank.",
        "guild_bank_rights_missing": "I don't have permission to deposit into the first guild-bank tab.",
        "guild_bank_full": "The first guild-bank tab is full.",
        "insufficient_surplus_gold": "I need to keep my operating reserve, so I can't share gold right now.",
        "verification_timeout": "I tried, but the action didn't complete.",
        "intent_expired": "That order expired before I could act on it.",
        "executor_restarted": "The worldserver restarted before I could finish that order.",
        "preempted_by_new_intent": "I switched to your newer order.",
    }.get(result_code, "I couldn't complete that order.")
