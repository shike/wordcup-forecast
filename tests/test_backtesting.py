"""Tests for the backtesting engine and metrics."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.backtesting.engine import BacktestEngine
from src.backtesting.metrics import compute_metrics, outcome_vector
from src.data.db import init_db
from src.data.repository import MatchRecord, MatchRepository


class TestMetrics(unittest.TestCase):
    def test_perfect_prediction(self):
        predictions = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
        outcomes = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
        metrics = compute_metrics(predictions, outcomes)
        self.assertAlmostEqual(metrics.rps, 0.0, places=6)
        self.assertAlmostEqual(metrics.log_loss, 0.0, places=6)
        self.assertAlmostEqual(metrics.brier, 0.0, places=6)
        self.assertEqual(metrics.accuracy, 1.0)

    def test_outcome_vector(self):
        self.assertEqual(outcome_vector(2, 1), (1.0, 0.0, 0.0))
        self.assertEqual(outcome_vector(1, 1), (0.0, 1.0, 0.0))
        self.assertEqual(outcome_vector(0, 1), (0.0, 0.0, 1.0))


class TestBacktestEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        init_db(self.db_path)
        repo = MatchRepository(self.db_path)
        repo.save_matches([
            MatchRecord(
                id="A-B-2024-01-01",
                date="2024-01-01",
                competition="Test",
                season="2024",
                stage=None,
                home_team_code="A",
                away_team_code="B",
                home_goals=2,
                away_goals=1,
                home_xg=None,
                away_xg=None,
                venue=None,
                neutral=True,
                source="test",
                fetched_at="2024-01-01T00:00:00",
            ),
            MatchRecord(
                id="A-C-2024-01-15",
                date="2024-01-15",
                competition="Test",
                season="2024",
                stage=None,
                home_team_code="A",
                away_team_code="C",
                home_goals=1,
                away_goals=0,
                home_xg=None,
                away_xg=None,
                venue=None,
                neutral=True,
                source="test",
                fetched_at="2024-01-15T00:00:00",
            ),
            MatchRecord(
                id="B-C-2024-01-20",
                date="2024-01-20",
                competition="Test",
                season="2024",
                stage=None,
                home_team_code="B",
                away_team_code="C",
                home_goals=0,
                away_goals=0,
                home_xg=None,
                away_xg=None,
                venue=None,
                neutral=True,
                source="test",
                fetched_at="2024-01-20T00:00:00",
            ),
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def test_runs_without_lookahead(self):
        engine = BacktestEngine(self.db_path)
        results = engine.run(competition="Test", season="2024")
        # First two matches have no prior history for at least one team and
        # are skipped. Only the final match (B vs C on 2024-01-20) is
        # evaluable because both teams have played one earlier match.
        self.assertEqual(len(results), 1)
        last = results[-1]
        self.assertEqual(last.actual_score, "0-0")
        self.assertAlmostEqual(sum(last.predicted_probs), 1.0, places=6)
        # And the predicted probabilities must reflect the prior data quality.
        self.assertEqual(last.sample_size_a, 1)
        self.assertEqual(last.sample_size_b, 1)


if __name__ == "__main__":
    unittest.main()
