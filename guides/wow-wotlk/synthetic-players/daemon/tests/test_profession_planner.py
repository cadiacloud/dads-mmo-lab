import unittest
from pathlib import Path

from synthetic_daemon.profession_planner import (
    ProfessionAssignment,
    ProfessionGuideCatalog,
    ProfessionPlanDocument,
)


GUIDES = Path(__file__).parents[1] / "config" / "profession-guides.yaml"


class ProfessionGuideCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = ProfessionGuideCatalog(str(GUIDES))

    def test_catalog_covers_all_gathering_skills_through_450(self) -> None:
        for skill_id in (182, 186, 393):
            _, profession = self.catalog.profession_for_skill(skill_id)
            self.assertEqual(profession["stages"][0]["skill_from"], 1)
            self.assertEqual(profession["stages"][-1]["skill_to"], 450)

    def test_assignment_schema_allowlists_every_stage_zone(self) -> None:
        schema = self.catalog.assignment_schema(
            {
                "bot_name": "Ray",
                "skill_id": 186,
                "current_skill": 1,
                "max_skill": 75,
            }
        )

        self.assertEqual(schema["properties"]["bot_name"]["const"], "Ray")
        self.assertEqual(schema["properties"]["profession"]["const"], "Mining")
        zones = schema["properties"]["stage_zones"]
        self.assertIs(zones["items"], False)
        self.assertEqual(zones["minItems"], len(zones["prefixItems"]))
        self.assertTrue(zones["prefixItems"][0]["enum"])

    def test_model_plan_is_restricted_to_expected_assignments_and_zones(self) -> None:
        current = [
            {
                "bot_name": "Ray",
                "bot_guid": 564,
                "skill_id": 393,
                "current_skill": 5,
                "max_skill": 75,
            }
        ]
        _, profession = self.catalog.profession_for_skill(393)
        choices = [stage["zones"][0]["name"] for stage in profession["stages"]]
        document = ProfessionPlanDocument(
            assignments=[
                ProfessionAssignment(
                    bot_name="Ray",
                    profession="Skinning",
                    stage_zones=choices,
                    rationale="Horde-friendly ground routes that follow Ray's level progression.",
                )
            ]
        )

        validated = self.catalog.validate_model_plan(document, current)
        rows = self.catalog.objective_rows(validated)

        self.assertEqual(len(validated), 1)
        self.assertEqual(len(rows), len(profession["stages"]))
        self.assertEqual(rows[0]["status"], "active")
        self.assertTrue(all(row["guild_bank_tab"] == 0 for row in rows))

    def test_rejects_model_selected_zone_outside_guide(self) -> None:
        current = [
            {
                "bot_name": "Ray",
                "bot_guid": 564,
                "skill_id": 393,
                "current_skill": 5,
                "max_skill": 75,
            }
        ]
        _, profession = self.catalog.profession_for_skill(393)
        choices = [stage["zones"][0]["name"] for stage in profession["stages"]]
        choices[0] = "Icecrown Citadel"
        document = ProfessionPlanDocument(
            assignments=[
                ProfessionAssignment(
                    bot_name="Ray",
                    profession="Skinning",
                    stage_zones=choices,
                    rationale="Invalid test route.",
                )
            ]
        )

        with self.assertRaisesRegex(ValueError, "disallowed zone"):
            self.catalog.validate_model_plan(document, current)


if __name__ == "__main__":
    unittest.main()
