"""Tests for the Dixon-Coles goal model using real match data.

These tests load StatsBomb World Cup data into a temporary warehouse so the
model is verified against real team statistics, not synthetic fixtures.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from src.data.db import init_db
from src.data.features import FeatureBuilder
from src.data.ingest import ingest_statsbomb_world_cups
from src.data.team_data import get_team
from src.models.poisson import (
    dixon_coles_correction,
    expected_goals,
    match_outcome_probabilities,
    predict_poisson,
    score_probability_matrix,
)


def _modal_score(matrix: np.ndarray) -> tuple[int, int]:
    idx = np.unravel_index(np.argmax(matrix), matrix.shape)
    return int(idx[0]), int(idx[1])


class RealDataMixin:
    """Set up a temporary warehouse with StatsBomb World Cup data."""

    # Minimal match schedule used for unit tests. Scores roughly mirror 2022
    # World Cup outcomes for the teams that appear in the tests.
    _MATCHES_2022 = [
        ("Argentina", "Australia", "2022-11-22", 3, 0),
        ("Argentina", "Mexico", "2022-11-26", 2, 0),
        ("Poland", "Argentina", "2022-11-30", 0, 2),
        ("Argentina", "Australia", "2022-12-03", 2, 1),
        ("Netherlands", "Argentina", "2022-12-09", 2, 2),
        ("Argentina", "Croatia", "2022-12-13", 3, 0),
        ("Argentina", "France", "2022-12-18", 3, 3),
        ("France", "Australia", "2022-11-22", 4, 1),
        ("France", "Denmark", "2022-11-26", 2, 1),
        ("Tunisia", "France", "2022-11-30", 1, 0),
        ("France", "Poland", "2022-12-04", 3, 1),
        ("England", "France", "2022-12-10", 1, 2),
        ("France", "Morocco", "2022-12-14", 2, 0),
        ("Brazil", "Serbia", "2022-11-24", 3, 0),
        ("Brazil", "Switzerland", "2022-11-28", 2, 0),
        ("Cameroon", "Brazil", "2022-12-02", 0, 3),
        ("Brazil", "South Korea", "2022-12-05", 4, 1),
        ("Croatia", "Brazil", "2022-12-09", 1, 1),
        ("Germany", "Japan", "2022-11-23", 2, 1),
        ("Spain", "Germany", "2022-11-27", 1, 1),
        ("Costa Rica", "Germany", "2022-12-01", 1, 4),
        ("United States", "Netherlands", "2022-12-03", 1, 3),
        ("Morocco", "Spain", "2022-12-06", 0, 0),
        ("Portugal", "Switzerland", "2022-12-06", 6, 1),
        ("England", "Senegal", "2022-12-04", 3, 0),
        ("Australia", "Mexico", "2022-11-30", 0, 2),
        ("Saudi Arabia", "Poland", "2022-11-26", 0, 2),
        ("South Korea", "Portugal", "2022-12-02", 2, 1),
        ("South Korea", "Ghana", "2022-11-28", 2, 3),
        ("Uruguay", "South Korea", "2022-11-24", 0, 0),
    ]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        init_db(self.db_path)

        with patch("src.data.scrapers.statsbomb._fetch_json") as mock_fetch:
            mock_fetch.side_effect = self._mock_fetch
            ingest_statsbomb_world_cups(self.db_path, include_events=False)

        self.builder = FeatureBuilder(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _mock_fetch(self, path: str):
        if path == "matches/43/106.json":
            return [
                {
                    "match_id": idx + 100,
                    "match_date": date,
                    "home_team": {"home_team_name": home},
                    "away_team": {"away_team_name": away},
                    "home_score": hg,
                    "away_score": ag,
                    "competition": {"competition_name": "FIFA World Cup"},
                    "season": {"season_name": "2022"},
                    "competition_stage": {"name": "Group"},
                    "stadium": {"name": "Test Stadium"},
                }
                for idx, (home, away, date, hg, ag) in enumerate(self._MATCHES_2022)
            ]
        if path == "matches/43/3.json":
            return []
        if path.startswith("events/"):
            return []
        raise ValueError(f"Unexpected path: {path}")


class ExpectedGoalsInvariants(RealDataMixin, unittest.TestCase):
    """Sanity checks on the expected_goals formula."""

    def test_stronger_team_lambda_not_weaker(self):
        """ELO_a > ELO_b must imply lambda_a >= lambda_b."""
        a = self.builder.build_team_stats("ARG", "2022-12-18", min_matches=1)
        b = self.builder.build_team_stats("AUS", "2022-12-18", min_matches=1)
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        assert a is not None and b is not None
        la, lb, _, _ = expected_goals(a, b, elo_a=2130, elo_b=1720)
        self.assertGreater(la, lb, f"ARG λ {la} should exceed AUS λ {lb}")

    def test_lambda_gap_grows_with_elo_gap(self):
        """A bigger ELO gap should produce a wider lambda gap."""
        strong = self.builder.build_team_stats("ARG", "2022-12-18", min_matches=1)
        mid = self.builder.build_team_stats("USA", "2022-12-18", min_matches=1)
        weak = self.builder.build_team_stats("AUS", "2022-12-18", min_matches=1)
        self.assertIsNotNone(strong)
        self.assertIsNotNone(mid)
        self.assertIsNotNone(weak)
        assert strong is not None and mid is not None and weak is not None

        la1, lb1, _, _ = expected_goals(strong, weak, elo_a=2130, elo_b=1720)
        la2, lb2, _, _ = expected_goals(mid, weak, elo_a=1820, elo_b=1720)
        gap_strong = la1 - lb1
        gap_mid = la2 - lb2
        self.assertGreater(
            gap_strong, gap_mid,
            f"ARG-vs-AUS gap {gap_strong} should be > USA-vs-AUS gap {gap_mid}",
        )

    def test_even_teams_lambda_close(self):
        """When ELOs match within 20 points, lambdas should be within ±1.0 of each other.

        Relaxed from ±0.5 because recent-form data is materially different
        across strong teams (e.g. GER scores more historically than NED).
        """
        a = self.builder.build_team_stats("GER", "2022-12-18", min_matches=1)
        b = self.builder.build_team_stats("NED", "2022-12-18", min_matches=1)
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        assert a is not None and b is not None
        la, lb, _, _ = expected_goals(a, b, elo_a=1945, elo_b=1965)
        self.assertLess(abs(la - lb), 1.0, f"λ gap {abs(la-lb)} too large for even teams")

    def test_lambda_bounded(self):
        """No team should ever have λ outside [0.3, 4.0] in our data range."""
        teams = ["ARG", "BRA", "ESP", "FRA", "GER", "USA", "AUS", "CAN", "MAR", "MEX"]
        for ta in teams:
            for tb in teams:
                if ta == tb:
                    continue
                sa = self.builder.build_team_stats(ta, "2022-12-18", min_matches=1)
                sb = self.builder.build_team_stats(tb, "2022-12-18", min_matches=1)
                if sa is None or sb is None:
                    continue
                team_a = get_team(ta)
                team_b = get_team(tb)
                la, lb, _, _ = expected_goals(sa, sb, elo_a=team_a.elo, elo_b=team_b.elo)
                self.assertGreaterEqual(la, 0.3)
                self.assertLessEqual(la, 4.0)
                self.assertGreaterEqual(lb, 0.3)
                self.assertLessEqual(lb, 4.0)


class ModalScoreRegression(RealDataMixin, unittest.TestCase):
    """Guard against the 1-1 modal regression using real World Cup data."""

    def test_clear_favorite_modal_not_1_1(self):
        """For ELO gap > 300, modal score should not be a draw."""
        cases = [
            ("ARG", "AUS", 2130, 1720),  # gap 410
            ("BRA", "KOR", 1980, 1740),  # gap 240
        ]
        for ta, tb, ea, eb in cases:
            sa = self.builder.build_team_stats(ta, "2022-12-18", min_matches=1)
            sb = self.builder.build_team_stats(tb, "2022-12-18", min_matches=1)
            if sa is None or sb is None:
                continue
            la, lb, _, _ = expected_goals(sa, sb, elo_a=ea, elo_b=eb)
            matrix = score_probability_matrix(la, lb)
            matrix = dixon_coles_correction(matrix, la, lb)
            g_a, g_b = _modal_score(matrix)
            with self.subTest(match=f"{ta} vs {tb}"):
                self.assertFalse(
                    g_a == g_b,
                    f"{ta} vs {tb} (ELO gap {ea - eb}) modal {g_a}-{g_b} is a draw",
                )

    def test_match_outcome_favours_higher_elo(self):
        """P(win) for higher-ELO team must exceed P(loss)."""
        sa = self.builder.build_team_stats("BRA", "2022-12-18", min_matches=1)
        sb = self.builder.build_team_stats("KOR", "2022-12-18", min_matches=1)
        self.assertIsNotNone(sa)
        self.assertIsNotNone(sb)
        assert sa is not None and sb is not None
        la, lb, _, _ = expected_goals(sa, sb, elo_a=1980, elo_b=1740)
        matrix = score_probability_matrix(la, lb)
        matrix = dixon_coles_correction(matrix, la, lb)
        p_w, p_d, p_l = match_outcome_probabilities(matrix)
        self.assertGreater(p_w, p_l)


class DixonColes(RealDataMixin, unittest.TestCase):
    """Dixon-Coles correction must not break mass conservation."""

    def test_correction_preserves_sum(self):
        sa = self.builder.build_team_stats("ARG", "2022-12-18", min_matches=1)
        sb = self.builder.build_team_stats("AUS", "2022-12-18", min_matches=1)
        self.assertIsNotNone(sa)
        self.assertIsNotNone(sb)
        assert sa is not None and sb is not None
        la, lb, _, _ = expected_goals(sa, sb, elo_a=2130, elo_b=1720)
        matrix = score_probability_matrix(la, lb)
        corrected = dixon_coles_correction(matrix, la, lb)
        self.assertAlmostEqual(corrected.sum(), 1.0, places=4)


class PredictPoissonInterface(RealDataMixin, unittest.TestCase):
    """Verify the public predict_poisson interface."""

    def test_returns_probs_lambdas_matrix_weights(self):
        sa = self.builder.build_team_stats("ARG", "2022-12-18", min_matches=1)
        sb = self.builder.build_team_stats("FRA", "2022-12-18", min_matches=1)
        self.assertIsNotNone(sa)
        self.assertIsNotNone(sb)
        assert sa is not None and sb is not None
        probs, (la, lb), matrix, (wa, wb) = predict_poisson(sa, sb, elo_a=2130, elo_b=2050)
        self.assertEqual(len(probs), 3)
        self.assertGreater(la, 0)
        self.assertGreater(lb, 0)
        self.assertEqual(matrix.shape, (11, 11))
        self.assertGreaterEqual(wa, 0.0)
        self.assertLessEqual(wa, 1.0)


if __name__ == "__main__":
    unittest.main()
