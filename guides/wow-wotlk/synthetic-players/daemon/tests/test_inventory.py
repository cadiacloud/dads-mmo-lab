import unittest

from synthetic_daemon.inventory import (
    contains_unverified_inventory_claim,
    is_inventory_query,
    render_inventory_response,
)


class InventoryGroundingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = {
            "age_seconds": 1,
            "money_copper": 123456,
            "free_bag_slots": 7,
            "bags": [
                {"entry": 2770, "count": 12, "name": "Copper Ore", "class": 7, "subclass": 7},
                {"entry": 37704, "count": 5, "name": "Crystallized Life", "class": 7, "subclass": 10},
                {"entry": 33448, "count": 3, "name": "Runic Mana Potion", "class": 0, "subclass": 1},
            ],
            "equipment": [
                {"entry": 50736, "count": 1, "name": "Heaven's Fall", "class": 2, "subclass": 15},
            ],
        }

    def test_identifies_inventory_questions_without_matching_orders(self) -> None:
        self.assertTrue(is_inventory_query("What materials do you have?"))
        self.assertTrue(is_inventory_query("How much copper ore do you have?"))
        self.assertTrue(is_inventory_query("Gear?"))
        self.assertFalse(is_inventory_query("Deposit your ore into the guild bank"))
        self.assertFalse(is_inventory_query("Follow me"))

    def test_reports_exact_requested_stack(self) -> None:
        self.assertEqual(
            render_inventory_response("Lyra", "How much copper ore do you have?", self.snapshot),
            "Verified 'copper ore': Copper Ore x12.",
        )

    def test_reports_absence_instead_of_inventing_an_item(self) -> None:
        self.assertEqual(
            render_inventory_response("Lyra", "Do you have any silk?", self.snapshot),
            "Verified bags: no item matching 'silk'.",
        )

    def test_material_and_gold_answers_are_grounded(self) -> None:
        materials = render_inventory_response("Lyra", "What materials do you have?", self.snapshot)
        self.assertIn("Copper Ore x12", materials)
        self.assertIn("Crystallized Life x5", materials)
        self.assertNotIn("Runic Mana Potion", materials)
        self.assertEqual(
            render_inventory_response("Lyra", "How much gold do you have?", self.snapshot),
            "Verified money: 12g 34s 56c.",
        )

    def test_stale_or_missing_snapshot_refuses_to_guess(self) -> None:
        self.assertEqual(
            render_inventory_response("Lyra", "What do you have?", None),
            "I can't verify my live inventory right now, so I won't guess.",
        )

    def test_blocks_model_authored_inventory_claims_but_not_ordinary_language(self) -> None:
        self.assertTrue(
            contains_unverified_inventory_claim(
                "I've got a stash of arcane crystals and some silk."
            )
        )
        self.assertTrue(contains_unverified_inventory_claim("I have twelve copper ore."))
        self.assertFalse(contains_unverified_inventory_claim("I have you covered."))
        self.assertFalse(contains_unverified_inventory_claim("Copper prices are climbing."))
        stale = {**self.snapshot, "age_seconds": 8}
        self.assertEqual(
            render_inventory_response("Lyra", "What do you have?", stale),
            "I can't verify my live inventory right now, so I won't guess.",
        )


if __name__ == "__main__":
    unittest.main()
