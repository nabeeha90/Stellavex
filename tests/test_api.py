"""API tests (need: pip install -r requirements.txt -r requirements-dev.txt).
Run:  python -m unittest discover -s tests"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ["STELLAVEX_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")

DESIGN = {"r": "condor", "b": "hydrolox", "f": 6000, "p": ["rover", "atmo", "relay"], "t": "slow", "w": "solar_l", "y": "bat_s", "a": "mga", "o": "high", "l": "opt"}


@unittest.skipIf(TestClient is None, "fastapi not installed")
class Api(unittest.TestCase):
    def setUp(self):
        import main

        self.c = TestClient(main.app)

    def test_health_and_catalog(self):
        self.assertTrue(self.c.get("/api/health").json()["ok"])
        self.assertIn("missions", self.c.get("/api/catalog").json())

    def test_simulate_is_deterministic(self):
        body = {"design": DESIGN, "mission": "mars", "seed": 42}
        self.assertEqual(self.c.post("/api/simulate", json=body).json(), self.c.post("/api/simulate", json=body).json())

    def test_bad_design_rejected(self):
        bad = dict(DESIGN, f=99999)
        self.assertEqual(self.c.post("/api/simulate", json={"design": bad, "mission": "mars"}).status_code, 422)

    def test_score_is_verified_and_ranked(self):
        body = {"name": "Test Pilot", "player_id": "abcdef123456", "mission": "mars", "seed": 7, "design": DESIGN, "choices": ["accept", "ride"]}
        r = self.c.post("/api/scores", json=body)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["score"], self.c.post("/api/simulate", json={"design": DESIGN, "mission": "mars", "seed": 7, "choices": ["accept", "ride"]}).json()["score"])
        board = self.c.get("/api/leaderboard?mission=mars").json()
        self.assertEqual(board[0]["name"], "Test Pilot")


if __name__ == "__main__":
    unittest.main()
