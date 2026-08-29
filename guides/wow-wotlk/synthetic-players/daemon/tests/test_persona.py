import unittest

from synthetic_daemon.config import DaemonSettings
from synthetic_daemon.persona import PersonaManager


class PersonaPromptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = PersonaManager(personas_file="/nonexistent/personas.yaml")

    def test_companion_prompt_is_friendly_first(self) -> None:
        persona = self.manager.get_or_create_persona("Lyra")
        prompt = self.manager.build_system_prompt(persona)

        self.assertIn("Treat the player and party as trusted friends", prompt)
        self.assertIn("Do not joke about a party member's competence", prompt)
        self.assertNotIn("Snarky", prompt)

    def test_mage_prompt_exposes_bounded_capability_contract(self) -> None:
        persona = self.manager.get_or_create_persona("Lyra")
        prompt = self.manager.build_system_prompt(persona)

        self.assertIn("[ACTION: PORTAL DESTINATION]", prompt)
        self.assertIn("[ACTION: REFRESHMENT]", prompt)
        self.assertIn("[ACTION: BUFF ARCANE BRILLIANCE]", prompt)
        self.assertIn("[INTENT: FOLLOW]", prompt)
        self.assertIn("[INTENT: PULL_PLAYER_TARGET]", prompt)
        self.assertIn("Never emit server, GM, shell, database, raw Playerbots", prompt)

    def test_celene_prompt_is_loyal_and_cap_aware(self) -> None:
        persona = self.manager.get_or_create_persona("Celene")
        prompt = self.manager.build_system_prompt(persona)

        self.assertEqual(persona.class_name, "Rogue")
        self.assertIn("loyal to the group", prompt)
        self.assertIn("Combat raid damage", prompt)
        self.assertIn("[INTENT: SAP_PLAYER_TARGET]", prompt)
        self.assertIn("Profession replacement", prompt)

    def test_leveling_personas_are_controlled_by_default(self) -> None:
        self.assertEqual(
            DaemonSettings().controlled_personas,
            ["Lyra", "Celene", "Ray", "Browntown"],
        )

    def test_ray_is_a_friendly_orc_rogue_with_requested_professions_and_quirk(self) -> None:
        persona = self.manager.get_or_create_persona("Ray")
        prompt = self.manager.build_system_prompt(persona)

        self.assertEqual(persona.race_name, "Orc")
        self.assertEqual(persona.class_name, "Rogue")
        self.assertIn("Combat PvE leveling", prompt)
        self.assertIn("Mining and Skinning", prompt)
        self.assertIn("Heh heh", prompt)
        self.assertIn("never belittles", prompt)

    def test_browntown_is_a_friendly_orc_mage_with_requested_professions(self) -> None:
        persona = self.manager.get_or_create_persona("Browntown")
        prompt = self.manager.build_system_prompt(persona)

        self.assertEqual(persona.race_name, "Orc")
        self.assertEqual(persona.class_name, "Mage")
        self.assertIn("Frost PvE leveling", prompt)
        self.assertIn("Herbalism and Mining", prompt)
        self.assertIn("never request free levels", prompt)


if __name__ == "__main__":
    unittest.main()
