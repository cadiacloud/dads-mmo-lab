from pathlib import Path
import unittest

from synthetic_daemon.material_kit_planner import (
    MaterialKitAssignment,
    MaterialKitCatalog,
    MaterialKitPlanner,
    ModeRoute,
)


CATALOG = Path(__file__).parents[1] / "config" / "material-kits.yaml"


class MaterialKitCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = MaterialKitCatalog(str(CATALOG))

    def test_requested_five_kits_are_source_backed(self) -> None:
        expected = {"alchemy", "inscription", "jewelcrafting", "engineering", "tailoring"}
        kits = self.catalog.selected_kits(sorted(expected))
        self.assertEqual(set(kits), expected)
        self.assertEqual(set(self.catalog.sources), expected)
        self.assertTrue(all(kit["materials"] for kit in kits.values()))

    def test_choice_dependent_finishing_routes_are_explicit(self) -> None:
        kits = self.catalog.selected_kits(["alchemy", "inscription", "jewelcrafting", "engineering", "tailoring"])

        def quantities(kit_name: str) -> dict[str, int]:
            return {
                material["name"]: int(material["count"])
                for material in kits[kit_name]["materials"]
            }

        self.assertIn("Flask of the Frost Wyrm", kits["alchemy"]["display_name"])
        self.assertEqual(quantities("alchemy")["Frost Lotus"], 15)
        self.assertEqual(quantities("alchemy")["Lichbloom"], 115)
        self.assertIn("recurring Northrend Inscription Research", kits["inscription"]["route_note"])
        self.assertEqual(quantities("jewelcrafting")["Dark Jade"], 30)
        self.assertEqual(quantities("jewelcrafting")["Crystallized Fire"], 300)
        self.assertEqual(quantities("tailoring")["Frostweave Cloth"], 5375)
        self.assertEqual(quantities("tailoring")["Infinite Dust"], 720)
        self.assertIn("RNG", self.catalog.data["quantity_basis"])

    def test_model_route_must_use_only_eligible_bots(self) -> None:
        eligible = {"mining": ["Celene", "Ray"]}
        valid = MaterialKitAssignment(
            routes=[ModeRoute(mode="mining", bot_names=["Celene", "Ray"], rationale="Share safe tiers.")]
        )
        self.assertEqual(
            MaterialKitPlanner._validate_assignment(valid, eligible),
            {"mining": ["Celene", "Ray"]},
        )

        invalid = MaterialKitAssignment(
            routes=[ModeRoute(mode="mining", bot_names=["Lyra"], rationale="Invalid skill assignment.")]
        )
        with self.assertRaisesRegex(ValueError, "ineligible"):
            MaterialKitPlanner._validate_assignment(invalid, eligible)


if __name__ == "__main__":
    unittest.main()
