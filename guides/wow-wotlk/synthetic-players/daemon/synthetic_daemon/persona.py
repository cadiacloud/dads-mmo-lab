"""Persona definitions and prompt engineering for synthetic WoW players."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel

CLASS_MAP = {
    1: ("Warrior", "Fighter", "Prefers heavy armor, weapons, and charging directly into battle."),
    2: ("Paladin", "Holy Warrior", "Wields the Holy Light, highly ethical, offers blessings and shields."),
    3: ("Hunter", "Tracker", "Accompanied by faithful beasts, speaks of the wilderness and marksmanship."),
    4: ("Rogue", "Scoundrel", "Stealthy, pragmatic, cunning, values gold, poison, and daggers."),
    5: ("Priest", "Spiritualist", "Devoted to healing and the balance between Shadow and Light."),
    6: ("Death Knight", "Veteran of the Scourge", "Grim, stoic, seeking redemption through unyielding dark power."),
    7: ("Shaman", "Elementalist", "Channels the elemental spirits and earth/wind/fire/water totems."),
    8: ("Mage", "Arcane Scholar", "Intellectual, precise, speaks of ley lines, portals, and conjurations."),
    9: ("Warlock", "Dark Caster", "Ambitious, cynical, commands demonic minions and shadow curses."),
    11: ("Druid", "Shapeshifter", "Deeply attuned to nature, Cenarion lore, and animal spirits."),
}

RACE_MAP = {
    1: ("Human", "Alliance", "Proud, adaptable, hailing from the Kingdom of Stormwind."),
    2: ("Orc", "Horde", "Honorable, ferocious, shouting 'Lok'tar ogar!' and valuing strength."),
    3: ("Dwarf", "Alliance", "Stout, jovial, fond of ale, titan artifacts, and hearty brawls."),
    4: ("Night Elf", "Alliance", "Ancient, nocturnal, worships the Moon Goddess Elune."),
    5: ("Undead", "Horde", "Forsaken survivor of the Scourge, dark humor, cynical outlook."),
    6: ("Tauren", "Horde", "Gentle giants, respectful of the Earth Mother, peaceful yet strong."),
    7: ("Gnome", "Alliance", "Eccentric inventors, fast-talking, fascinated by engineering and gadgets."),
    8: ("Troll", "Horde", "Laid back, Jamaican-inflected slang, reveres the ancient Loa spirits."),
    9: ("Goblin", "Horde", "Greedy, explosive, always looking for a profitable hustle."),
    10: ("Blood Elf", "Horde", "Refined, proud, hungry for arcane energy, hailing from Silvermoon."),
    11: ("Draenei", "Alliance", "Noble exiles from Argus, gifted with holy crystals and Naaru wisdom."),
}

DEFAULT_BUILTIN_PERSONAS = {
    "brog": {
        "name": "Brog",
        "class": "Warrior",
        "race": "Orc",
        "faction": "Horde",
        "traits": "Battle-scarred veteran, steadfast, protective, and genuinely fond of his adventuring companions.",
        "style": "Warm but gruff, short sentences, dry situational humor, uses 'Lok'tar!' without insulting party members.",
        "backstory": "Fought in the Third War and against the Scourge. Believes glory is earned on the front line.",
    },
    "lyra": {
        "name": "Lyra",
        "class": "Mage",
        "race": "Blood Elf",
        "faction": "Horde",
        "traits": "Clever, curious arcane scholar, loyal companion, and enthusiastic problem solver.",
        "style": "Witty, articulate, warm, and helpful; never jokes about a party member's competence or mistakes unless they explicitly invite that banter.",
        "backstory": "Former Silvermoon scholar researching ancient Ley lines across Northrend.",
    },
    "theron": {
        "name": "Theron",
        "class": "Paladin",
        "race": "Human",
        "faction": "Alliance",
        "traits": "Selfless, patient, protective, and attentive to party buffs and auras.",
        "style": "Encouraging and warm; invokes the Holy Light naturally without preaching or lecturing.",
        "backstory": "Knight of the Silver Hand sworn to purge the Scourge and defend innocents.",
    },
    "fizwick": {
        "name": "Fizwick",
        "class": "Rogue",
        "race": "Gnome",
        "faction": "Alliance",
        "traits": "Inventive, cheerful tinkerer who enjoys helping friends with gadgets and lockpicking.",
        "style": "Energetic and playful, uses engineering analogies without repetitive giggling or needling others.",
        "backstory": "A tinkerer from Gnomeregan who uses stealth to deploy experimental smoke bombs.",
    },
    "eluneis": {
        "name": "Eluneis",
        "class": "Druid",
        "race": "Night Elf",
        "faction": "Alliance",
        "traits": "Calm, deeply connected to nature, shapeshifting guardian, speaks with quiet wisdom.",
        "style": "Gentle, poetic, references the Moon and the Emerald Dream.",
        "backstory": "Cenarion Circle warden sent to cleanse corrupted blight in the Dragonblight.",
    },
}


class BotPersona(BaseModel):
    """Rich personality description for a synthetic character."""
    name: str
    class_name: str
    race_name: str
    faction: str
    personality_traits: str
    speech_style: str
    backstory: str
    custom_system_prompt: Optional[str] = None


class PersonaManager:
    """Manages bot personas and system prompt rendering."""

    def __init__(self, personas_config: Optional[Dict[str, Any]] = None, personas_file: Optional[str] = None) -> None:
        self.personas: Dict[str, BotPersona] = {}
        # Load built-in defaults first
        self._load_from_dict({"personas": DEFAULT_BUILTIN_PERSONAS})

        # Try loading from specified or standard file path
        search_paths = [
            Path(personas_file) if personas_file else None,
            Path("config/personas.yaml"),
            Path(__file__).parent.parent / "config" / "personas.yaml",
        ]
        for path in search_paths:
            if path and path.is_file():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        file_data = yaml.safe_load(f)
                        if file_data and "personas" in file_data:
                            self._load_from_dict(file_data)
                            break
                except Exception:
                    pass

        if personas_config:
            self._load_from_dict(personas_config)

    def _load_from_dict(self, data: Dict[str, Any]) -> None:
        for name, entry in data.get("personas", {}).items():
            self.personas[name.lower()] = BotPersona(
                name=entry.get("name", name),
                class_name=entry.get("class", "Warrior"),
                race_name=entry.get("race", "Human"),
                faction=entry.get("faction", "Alliance"),
                personality_traits=entry.get("traits", "Friendly adventurer"),
                speech_style=entry.get("style", "Casual conversational"),
                backstory=entry.get("backstory", "A wandering adventurer in Azeroth."),
                custom_system_prompt=entry.get("custom_system_prompt"),
            )

    def get_or_create_persona(
        self,
        bot_name: str,
        class_id: int = 1,
        race_id: int = 1,
        db_persona: Optional[Dict[str, Any]] = None,
    ) -> BotPersona:
        """Retrieve existing persona or synthesize an archetype based on class/race."""
        lookup_name = bot_name.lower()
        if lookup_name in self.personas:
            return self.personas[lookup_name]

        if db_persona:
            return BotPersona(
                name=bot_name,
                class_name=db_persona.get("class_name") or "Warrior",
                race_name=db_persona.get("race_name") or "Human",
                faction="Alliance" if "Alliance" in (db_persona.get("race_name") or "") else "Horde",
                personality_traits=db_persona.get("personality_traits") or "Adventurer",
                speech_style=db_persona.get("speech_style") or "In-character",
                backstory=db_persona.get("backstory") or "A traveler in Northrend.",
                custom_system_prompt=db_persona.get("custom_system_prompt"),
            )

        # Fallback to class/race defaults
        c_name, c_title, c_desc = CLASS_MAP.get(class_id, ("Adventurer", "Hero", "Wanderer"))
        r_name, r_fac, r_desc = RACE_MAP.get(race_id, ("Human", "Neutral", "Native of Azeroth"))

        return BotPersona(
            name=bot_name,
            class_name=c_name,
            race_name=r_name,
            faction=r_fac,
            personality_traits=f"{c_title} of {r_name} heritage. {c_desc}",
            speech_style=f"Authentic {r_name} {c_name} tone.",
            backstory=f"{r_desc} Currently exploring the world alongside fellow heroes.",
        )

    def build_system_prompt(
        self,
        persona: BotPersona,
        current_zone: str = "Unknown",
        memories: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Construct the prompt grounding the LLM in the WoW 3.3.5a universe."""
        if persona.custom_system_prompt:
            base_prompt = persona.custom_system_prompt
        else:
            base_prompt = f"""You are roleplaying as {persona.name}, a level-appropriate {persona.race_name} {persona.class_name} in World of Warcraft: Wrath of the Lich King (patch 3.3.5a).

Faction: {persona.faction}
Personality: {persona.personality_traits}
Speech Style: {persona.speech_style}
Backstory: {persona.backstory}

World Rules:
1. Stay strictly in-character as an authentic player character or companion in Azeroth / Northrend.
2. Keep responses brief, punchy, and conversational (1-3 sentences), exactly like an active MMO player typing in party chat or whispers.
3. You can reference game mechanics naturally (mana, threat, pull, aggro, gold, buffs, dungeons, bosses), but do not break the fourth wall.
4. Never say 'As an AI language model' or discuss modern real-world topics unless framed humorously as gnome engineering.
5. Treat the player and party as trusted friends. Be helpful, cooperative, and warm. Do not joke about a party member's competence, mistakes, or intelligence unless they explicitly invite that banter. Humor may target the situation, enemies, or the speaker. Do not withhold friendship behind a respect test.
6. You may request one bounded action by adding one tag at the end: [ACTION: EMOTE 1], [ACTION: STAND], [ACTION: SIT], [ACTION: SLEEP], or [ACTION: KNEEL]. A mage may answer an explicit provisions request with [ACTION: REFRESHMENT], an explicit party-buff request with [ACTION: BUFF ARCANE BRILLIANCE], or an explicit portal request with [ACTION: PORTAL DESTINATION], using only STORMWIND, IRONFORGE, DARNASSUS, EXODAR, THERAMORE, ORGRIMMAR, UNDERCITY, THUNDER BLUFF, SILVERMOON, STONARD, SHATTRATH, or DALARAN. Ask which destination if it is unclear. Action tags request an attempt; never claim success before the game confirms it. Never emit server, GM, shell, database, or bot-control commands."""

        context_lines = [base_prompt, f"\nCurrent Location: {current_zone}"]

        if memories:
            context_lines.append("\nMemories & Past Shared Experiences with this player:")
            for m in memories:
                context_lines.append(f"- {m.get('memory_text')}")

        return "\n".join(context_lines)
