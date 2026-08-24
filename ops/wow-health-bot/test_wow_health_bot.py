import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("wow_health_bot.py")
SPEC = importlib.util.spec_from_file_location("wow_health_bot", MODULE_PATH)
assert SPEC and SPEC.loader
BOT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BOT
SPEC.loader.exec_module(BOT)


class PayloadTests(unittest.TestCase):
    def test_healthy_payload(self):
        payload = BOT.discord_payload([BOT.Check("World", True, "running")], reason="startup")
        embed = payload["embeds"][0]
        self.assertIn("ONLINE", embed["title"])
        self.assertEqual({"parse": []}, payload["allowed_mentions"])

    def test_degraded_payload(self):
        payload = BOT.discord_payload([BOT.Check("World", False, "missing")], reason="state changed")
        self.assertIn("DEGRADED", payload["embeds"][0]["title"])

    def test_fingerprint_is_stable(self):
        checks = [BOT.Check("World", True, "running")]
        self.assertEqual(BOT.fingerprint(checks), BOT.fingerprint(checks))


if __name__ == "__main__":
    unittest.main()
