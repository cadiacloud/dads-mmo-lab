import unittest

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
        self.assertIn("Never emit server, GM, shell, database, or bot-control commands", prompt)


if __name__ == "__main__":
    unittest.main()
