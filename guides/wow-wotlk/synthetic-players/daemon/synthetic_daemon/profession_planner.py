"""Allowlisted LLM planning for WotLK gathering professions."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Annotated, Any, Dict, Iterable, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field
import yaml

from .config import DaemonSettings
from .db import DatabaseManager
from .llm_client import SyntheticLLMClient


GATHERING_SKILL_NAMES = {
    182: "Herbalism",
    186: "Mining",
    393: "Skinning",
}


class ProfessionAssignment(BaseModel):
    """Compact model output: one validated zone choice per fixed guide stage."""

    model_config = ConfigDict(extra="forbid")

    bot_name: str
    profession: str
    stage_zones: List[Annotated[str, Field(min_length=1, max_length=64)]]
    rationale: str = Field(min_length=1, max_length=500)


class ProfessionPlanDocument(BaseModel):
    """Schema-constrained plan returned by the local model."""

    model_config = ConfigDict(extra="forbid")

    assignments: List[ProfessionAssignment]


@dataclass(frozen=True)
class ValidatedAssignment:
    bot_name: str
    bot_guid: int
    profession_key: str
    profession_name: str
    skill_id: int
    current_skill: int
    stage_zones: Tuple[str, ...]
    rationale: str


class ProfessionGuideCatalog:
    """Validated local projection of the cited 1-450 gathering guides."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        with self.path.open("r", encoding="utf-8") as stream:
            self.data: Dict[str, Any] = yaml.safe_load(stream) or {}
        self._validate()

    def _validate(self) -> None:
        if self.data.get("version") != 1:
            raise ValueError("Unsupported profession guide version")
        sources = self.data.get("sources")
        professions = self.data.get("professions")
        if not isinstance(sources, dict) or not isinstance(professions, dict):
            raise ValueError("Profession guide must declare sources and professions")

        seen_skill_ids = set()
        for key, profession in professions.items():
            skill_id = int(profession.get("skill_id") or 0)
            if not skill_id or skill_id in seen_skill_ids:
                raise ValueError(f"Invalid or duplicate skill_id for {key}")
            seen_skill_ids.add(skill_id)
            stages = profession.get("stages") or []
            if not stages:
                raise ValueError(f"Profession {key} has no stages")
            previous_to: Optional[int] = None
            for index, stage in enumerate(stages):
                skill_from = int(stage.get("skill_from") or 0)
                skill_to = int(stage.get("skill_to") or 0)
                if skill_from < 1 or skill_to <= skill_from:
                    raise ValueError(f"Invalid {key} stage {index}")
                if previous_to is not None and skill_from != previous_to:
                    raise ValueError(f"Non-contiguous {key} stage {index}")
                if not stage.get("materials") or not stage.get("zones"):
                    raise ValueError(f"Incomplete {key} stage {index}")
                for zone in stage["zones"]:
                    if not zone.get("name") or int(zone.get("zone_id") or 0) <= 0:
                        raise ValueError(f"Invalid zone in {key} stage {index}")
                previous_to = skill_to
            if stages[0]["skill_from"] != 1 or stages[-1]["skill_to"] != 450:
                raise ValueError(f"Profession {key} must cover skill 1 through 450")
            if key not in sources or not str(sources[key]).startswith("https://"):
                raise ValueError(f"Profession {key} has no HTTPS source")

    @property
    def version(self) -> int:
        return int(self.data["version"])

    @property
    def sources(self) -> Dict[str, str]:
        return {str(key): str(value) for key, value in self.data["sources"].items()}

    @property
    def bank_policy(self) -> Dict[str, Any]:
        return dict(self.data.get("bank_policy") or {})

    def profession_for_skill(self, skill_id: int) -> Tuple[str, Dict[str, Any]]:
        for key, profession in self.data["professions"].items():
            if int(profession["skill_id"]) == skill_id:
                return key, profession
        raise KeyError(skill_id)

    def planning_prompt(self, assignments: Iterable[Dict[str, Any]]) -> str:
        lines = [
            "Create a conservative WotLK 3.3.5a gathering plan.",
            "Return exactly one assignment for every bot/profession listed below.",
            "For each stage choose exactly one zone from that stage's allowed zones, in stage order.",
            "These bots level with real players: prefer Horde-friendly, level-appropriate, non-flying routes.",
            "Do not change professions, grant skill, create materials, select a different skill range, or omit a stage.",
            "All harvested profession materials will be deposited into guild-bank tab 0 by deterministic code.",
            "Required assignments:",
        ]
        for assignment in assignments:
            profession_key, profession = self.profession_for_skill(int(assignment["skill_id"]))
            lines.append(
                f"- {assignment['bot_name']} / {profession['display_name']} "
                f"(current {assignment['current_skill']}/{assignment['max_skill']}):"
            )
            for index, stage in enumerate(profession["stages"], start=1):
                choices = ", ".join(zone["name"] for zone in stage["zones"])
                lines.append(
                    f"  stage {index} [{stage['skill_from']}-{stage['skill_to']}], "
                    f"minimum character level {stage['min_character_level']}: {choices}"
                )
            lines.append(f"  profession key: {profession_key}")
        return "\n".join(lines)

    def assignment_schema(self, assignment: Dict[str, Any]) -> Dict[str, Any]:
        """Build a grammar whose every stage value is a guide allowlist enum."""
        _, profession = self.profession_for_skill(int(assignment["skill_id"]))
        return {
            "type": "object",
            "properties": {
                "bot_name": {"type": "string", "const": str(assignment["bot_name"])},
                "profession": {"type": "string", "const": str(profession["display_name"])},
                "stage_zones": {
                    "type": "array",
                    "prefixItems": [
                        {
                            "type": "string",
                            "enum": [str(zone["name"]) for zone in stage["zones"]],
                        }
                        for stage in profession["stages"]
                    ],
                    "items": False,
                    "minItems": len(profession["stages"]),
                    "maxItems": len(profession["stages"]),
                },
                "rationale": {"type": "string", "minLength": 1, "maxLength": 200},
            },
            "required": ["bot_name", "profession", "stage_zones", "rationale"],
            "additionalProperties": False,
        }

    def validate_model_plan(
        self,
        document: ProfessionPlanDocument,
        assignments: Iterable[Dict[str, Any]],
    ) -> List[ValidatedAssignment]:
        expected: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for assignment in assignments:
            profession_key, profession = self.profession_for_skill(int(assignment["skill_id"]))
            expected[(assignment["bot_name"].casefold(), profession["display_name"].casefold())] = assignment

        supplied: Dict[Tuple[str, str], ProfessionAssignment] = {}
        for assignment in document.assignments:
            key = (assignment.bot_name.casefold(), assignment.profession.casefold())
            if key in supplied:
                raise ValueError(f"Duplicate LLM assignment for {assignment.bot_name}/{assignment.profession}")
            supplied[key] = assignment
        if set(supplied) != set(expected):
            missing = sorted(set(expected) - set(supplied))
            extra = sorted(set(supplied) - set(expected))
            raise ValueError(f"LLM plan assignment mismatch; missing={missing}, extra={extra}")

        validated = []
        for key, current in expected.items():
            model_assignment = supplied[key]
            profession_key, profession = self.profession_for_skill(int(current["skill_id"]))
            stages = profession["stages"]
            if len(model_assignment.stage_zones) != len(stages):
                raise ValueError(
                    f"{model_assignment.bot_name}/{model_assignment.profession} returned "
                    f"{len(model_assignment.stage_zones)} zones for {len(stages)} stages"
                )
            for index, (selected, stage) in enumerate(zip(model_assignment.stage_zones, stages), start=1):
                allowed = {zone["name"] for zone in stage["zones"]}
                if selected not in allowed:
                    raise ValueError(
                        f"LLM selected disallowed zone {selected!r} for "
                        f"{model_assignment.profession} stage {index}"
                    )
            validated.append(
                ValidatedAssignment(
                    bot_name=str(current["bot_name"]),
                    bot_guid=int(current["bot_guid"]),
                    profession_key=profession_key,
                    profession_name=str(profession["display_name"]),
                    skill_id=int(current["skill_id"]),
                    current_skill=int(current["current_skill"]),
                    stage_zones=tuple(model_assignment.stage_zones),
                    rationale=model_assignment.rationale,
                )
            )
        return validated

    def objective_rows(self, assignments: Iterable[ValidatedAssignment]) -> List[Dict[str, Any]]:
        rows = []
        bank_policy = self.bank_policy
        for assignment in assignments:
            profession = self.data["professions"][assignment.profession_key]
            source_url = self.sources[assignment.profession_key]
            for stage_order, (stage, selected_zone) in enumerate(
                zip(profession["stages"], assignment.stage_zones),
                start=1,
            ):
                zone = next(zone for zone in stage["zones"] if zone["name"] == selected_zone)
                current = assignment.current_skill
                status = "completed" if current >= int(stage["skill_to"]) else (
                    "active" if int(stage["skill_from"]) <= current < int(stage["skill_to"]) else "queued"
                )
                rows.append(
                    {
                        "bot_guid": assignment.bot_guid,
                        "bot_name": assignment.bot_name,
                        "profession": assignment.profession_name,
                        "skill_id": assignment.skill_id,
                        "stage_order": stage_order,
                        "skill_from": int(stage["skill_from"]),
                        "skill_to": int(stage["skill_to"]),
                        "min_character_level": int(stage["min_character_level"]),
                        "selected_zone": selected_zone,
                        "selected_zone_id": int(zone["zone_id"]),
                        "materials_json": json.dumps(stage["materials"], separators=(",", ":")),
                        "tool_item_id": int(profession.get("tool_item_id") or 0),
                        "deposit_category": str(profession["deposit_category"]),
                        "guild_bank_tab": int(bank_policy.get("guild_tab", 0)),
                        "deposit_free_slots": int(bank_policy.get("deposit_when_free_slots_below", 6)),
                        "source_url": source_url,
                        "status": status,
                        "last_observed_skill": current,
                    }
                )
        return rows


class ProfessionPlanner:
    """Ask the local LLM to choose routes, validate them, and persist objectives."""

    def __init__(self, settings: DaemonSettings, guides_file: str) -> None:
        self.settings = settings
        self.catalog = ProfessionGuideCatalog(guides_file)
        self.db = DatabaseManager(settings.db)
        self.llm = SyntheticLLMClient(settings.llm)

    async def close(self) -> None:
        await self.llm.close()
        await self.db.close()

    async def create_and_activate(
        self,
        bot_names: Optional[List[str]] = None,
        authorized_by: str = "Michael Nicolai",
        authorization_note: str = "Owner instruction in authenticated chat on 2026-08-29",
    ) -> Tuple[int, List[ValidatedAssignment], int]:
        await self.db.connect()
        current = await self.db.list_gathering_professions(
            bot_names or self.settings.controlled_personas
        )
        if not current:
            raise RuntimeError("No controlled persona has a learned gathering profession")

        system_prompt = (
            "You are Cadia's bounded WotLK profession planner. You select only from the supplied "
            "guide stages and zone choices. You do not grant items, levels, skill points, professions, "
            "or authority. Deterministic server code validates and executes every objective."
        )
        model_assignments = []
        for assignment in current:
            profession_key, _ = self.catalog.profession_for_skill(int(assignment["skill_id"]))
            raw_assignment = await self.llm.generate_structured_json(
                system_prompt=system_prompt,
                user_message=self.catalog.planning_prompt([assignment]),
                schema_name=(
                    f"wotlk_{str(assignment['bot_name']).casefold()}_{profession_key}"
                    .replace(" ", "_")
                ),
                json_schema=self.catalog.assignment_schema(assignment),
                max_tokens=1024,
            )
            model_assignments.append(ProfessionAssignment.model_validate(raw_assignment))
        document = ProfessionPlanDocument(assignments=model_assignments)
        validated = self.catalog.validate_model_plan(document, current)
        rows = self.catalog.objective_rows(validated)
        plan_id = await self.db.replace_profession_objectives(
            planner_model=self.settings.llm.model,
            guide_version=self.catalog.version,
            plan_json=document.model_dump(mode="json"),
            source_urls=self.catalog.sources,
            assignments=validated,
            objective_rows=rows,
            authorized_by=authorized_by,
            authorization_note=authorization_note,
        )
        return plan_id, validated, len(rows)
