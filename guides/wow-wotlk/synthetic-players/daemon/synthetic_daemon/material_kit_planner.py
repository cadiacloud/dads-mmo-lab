"""Source-backed profession material kits with bounded LLM work allocation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field
import yaml

from .config import DaemonSettings
from .db import DatabaseManager
from .llm_client import SyntheticLLMClient


MODE_SKILLS = {"herbalism": 182, "mining": 186, "skinning": 393}
MODE_CATEGORIES = {
    "herbalism": "herbalism",
    "mining": "mining",
    "skinning": "skinning",
    "loot": "cloth",
    "auction": "economy",
}
OUTLAND_ZONES = {3483, 3518, 3519, 3520, 3521, 3522, 3523}
NORTHREND_ZONES = {65, 66, 67, 210, 3537, 394, 495, 3711}


class ModeRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str
    bot_names: List[str] = Field(min_length=1)
    rationale: str = Field(min_length=1, max_length=240)


class MaterialKitAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    routes: List[ModeRoute]


@dataclass(frozen=True)
class PersonaCapability:
    bot_name: str
    bot_guid: int
    character_level: int
    guild_id: int
    skill_ids: frozenset[int]


class MaterialKitCatalog:
    """Validated local projection of source shopping lists."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        with self.path.open("r", encoding="utf-8") as stream:
            self.data: Dict[str, Any] = yaml.safe_load(stream) or {}
        self._validate()

    def _validate(self) -> None:
        if self.data.get("version") != 1:
            raise ValueError("Unsupported material-kit catalog version")
        sources = self.data.get("sources")
        kits = self.data.get("kits")
        if not isinstance(sources, dict) or not isinstance(kits, dict) or not kits:
            raise ValueError("Material-kit catalog must declare sources and kits")

        for key, kit in kits.items():
            if key not in sources or not str(sources[key]).startswith("https://"):
                raise ValueError(f"Kit {key} has no HTTPS source")
            materials = kit.get("materials") or []
            if not materials:
                raise ValueError(f"Kit {key} has no materials")
            for index, material in enumerate(materials, start=1):
                if not str(material.get("name") or "").strip():
                    raise ValueError(f"Kit {key} material {index} has no name")
                if int(material.get("count") or 0) <= 0:
                    raise ValueError(f"Kit {key} material {index} has an invalid count")
                if material.get("mode") not in MODE_CATEGORIES:
                    raise ValueError(f"Kit {key} material {index} has an invalid acquisition mode")
                if not str(material.get("zone") or "") or int(material.get("zone_id") or 0) <= 0:
                    raise ValueError(f"Kit {key} material {index} has no bounded zone")

    @property
    def version(self) -> int:
        return int(self.data["version"])

    @property
    def sources(self) -> Dict[str, str]:
        return {str(key): str(value) for key, value in self.data["sources"].items()}

    def selected_kits(self, professions: Iterable[str]) -> Dict[str, Dict[str, Any]]:
        requested = [name.casefold() for name in professions]
        missing = sorted(set(requested) - set(self.data["kits"]))
        if missing:
            raise ValueError(f"Unknown profession kit(s): {', '.join(missing)}")
        return {name: self.data["kits"][name] for name in requested}


class MaterialKitPlanner:
    """Let the local LLM schedule only which qualified bots share fixed work."""

    def __init__(self, settings: DaemonSettings, catalog_file: str) -> None:
        self.settings = settings
        self.catalog = MaterialKitCatalog(catalog_file)
        self.db = DatabaseManager(settings.db)
        self.llm = SyntheticLLMClient(settings.llm)

    async def close(self) -> None:
        await self.llm.close()
        await self.db.close()

    @staticmethod
    def _capabilities(rows: List[Dict[str, Any]]) -> Dict[str, PersonaCapability]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            key = str(row["bot_name"]).casefold()
            current = grouped.setdefault(
                key,
                {
                    "bot_name": str(row["bot_name"]),
                    "bot_guid": int(row["bot_guid"]),
                    "character_level": int(row["character_level"]),
                    "guild_id": int(row.get("guild_id") or 0),
                    "skill_ids": set(),
                },
            )
            current["skill_ids"].add(int(row["skill_id"]))
        return {
            key: PersonaCapability(
                bot_name=value["bot_name"],
                bot_guid=value["bot_guid"],
                character_level=value["character_level"],
                guild_id=value["guild_id"],
                skill_ids=frozenset(value["skill_ids"]),
            )
            for key, value in grouped.items()
        }

    @staticmethod
    def _eligible_by_mode(
        capabilities: Dict[str, PersonaCapability], modes: Iterable[str]
    ) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        for mode in modes:
            required_skill = MODE_SKILLS.get(mode)
            eligible = [
                capability.bot_name
                for capability in capabilities.values()
                if capability.guild_id and (
                    required_skill is None or required_skill in capability.skill_ids
                )
            ]
            if not eligible:
                raise RuntimeError(f"No guilded controlled persona can perform {mode}")
            result[mode] = sorted(eligible)
        return result

    @staticmethod
    def _assignment_schema(mode: str, eligible: List[str]) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "bot_names": {
                    "type": "array",
                    "items": {"type": "string", "enum": eligible},
                    "minItems": 1,
                    "maxItems": len(eligible),
                },
                "rationale": {"type": "string", "minLength": 1, "maxLength": 240},
            },
            "required": ["bot_names", "rationale"],
            "additionalProperties": False,
        }

    @staticmethod
    def _minimum_level(zone_id: int) -> int:
        if zone_id in NORTHREND_ZONES:
            return 68
        if zone_id in OUTLAND_ZONES:
            return 58
        return 1

    @staticmethod
    def _validate_assignment(
        document: MaterialKitAssignment,
        eligible: Dict[str, List[str]],
    ) -> Dict[str, List[str]]:
        supplied = {route.mode: route.bot_names for route in document.routes}
        if set(supplied) != set(eligible):
            raise ValueError("LLM material-route modes did not match the required modes")
        for mode, names in supplied.items():
            if not names or not set(names).issubset(set(eligible[mode])):
                raise ValueError(f"LLM assigned an ineligible bot to {mode}")
        return supplied

    async def create_and_activate(
        self,
        professions: List[str],
        authorized_by: str = "Michael Nicolai",
        authorization_note: str = "Owner instruction in authenticated chat on 2026-08-29",
    ) -> Tuple[int, MaterialKitAssignment, int]:
        await self.db.connect()
        kits = self.catalog.selected_kits(professions)
        current = await self.db.list_gathering_professions(self.settings.controlled_personas)
        capabilities = self._capabilities(current)
        modes = sorted(
            {str(material["mode"]) for kit in kits.values() for material in kit["materials"]}
        )
        eligible = self._eligible_by_mode(capabilities, modes)

        prompt_lines = [
            "Allocate fixed WotLK profession-kit work among eligible persona bots.",
            "You may only order the supplied eligible bot names for each acquisition mode.",
            "Prefer level-80 bots for Outland/Northrend work and let leveling bots contribute in safe old-world zones.",
            "Do not change item names, counts, professions, skill values, sources, zones, guild rules, or authority.",
        ]
        for mode in sorted(eligible):
            prompt_lines.append(f"- {mode}: {', '.join(eligible[mode])}")
        prompt_lines.append(f"Requested kits: {', '.join(kits)}")
        routes = []
        for mode in sorted(eligible):
            raw = await self.llm.generate_structured_json(
                system_prompt=(
                    "You are Cadia's bounded WotLK work allocator. Deterministic server code owns "
                    "all quantities, inventory counts, deposits, travel bounds, and execution."
                ),
                user_message="\n".join(prompt_lines) + f"\nReturn only the work order for mode: {mode}",
                schema_name=f"wotlk_material_kit_{mode}",
                json_schema=self._assignment_schema(mode, eligible[mode]),
                max_tokens=384,
            )
            routes.append(
                ModeRoute(
                    mode=mode,
                    bot_names=list(raw["bot_names"]),
                    rationale=str(raw["rationale"]),
                )
            )
        document = MaterialKitAssignment(routes=routes)
        route_order = self._validate_assignment(document, eligible)

        item_names = [
            str(material["name"])
            for kit in kits.values()
            for material in kit["materials"]
        ]
        item_entries = await self.db.resolve_material_item_entries(item_names)
        missing_items = sorted(set(item_names) - set(item_entries))
        if missing_items:
            raise RuntimeError(f"Catalog item names missing from acore_world: {missing_items}")

        thresholds: Dict[str, int] = {}
        mode_offsets: Dict[str, int] = {mode: 0 for mode in modes}
        targets: List[Dict[str, Any]] = []
        for profession_key, kit in kits.items():
            for stage_order, material in enumerate(kit["materials"], start=1):
                mode = str(material["mode"])
                candidates = [capabilities[name.casefold()] for name in route_order[mode]]
                min_level = self._minimum_level(int(material["zone_id"]))
                qualified = [candidate for candidate in candidates if candidate.character_level >= min_level]
                pool = qualified or candidates
                selected = pool[mode_offsets[mode] % len(pool)]
                mode_offsets[mode] += 1

                item_name = str(material["name"])
                required = int(material["count"])
                thresholds[item_name] = thresholds.get(item_name, 0) + required
                status = "queued" if selected.character_level >= min_level and mode != "auction" else "waiting"
                targets.append(
                    {
                        "profession_key": profession_key,
                        "profession_name": str(kit["display_name"]),
                        "stage_order": stage_order,
                        "item_entry": item_entries[item_name],
                        "item_name": item_name,
                        "required_count": required,
                        "bank_threshold": thresholds[item_name],
                        "bot_guid": selected.bot_guid,
                        "bot_name": selected.bot_name,
                        "gathering_skill_id": MODE_SKILLS.get(mode, 0),
                        "acquisition_mode": mode,
                        "deposit_category": MODE_CATEGORIES[mode],
                        "selected_zone": str(material["zone"]),
                        "selected_zone_id": int(material["zone_id"]),
                        "min_character_level": min_level,
                        "guild_id": selected.guild_id,
                        "guild_bank_tab": 0,
                        "source_url": self.catalog.sources[profession_key],
                        "status": status,
                    }
                )

        plan_id = await self.db.replace_material_kit_targets(
            planner_model=self.settings.llm.model,
            catalog_version=self.catalog.version,
            professions=list(kits),
            assignment_json=document.model_dump(mode="json"),
            source_urls={key: self.catalog.sources[key] for key in kits},
            target_rows=targets,
            authorized_by=authorized_by,
            authorization_note=authorization_note,
        )
        return plan_id, document, len(targets)
