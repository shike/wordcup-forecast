"""Tests for the real-data warehouse layer.

These tests verify that match records, repositories, and feature builders
work with real data patterns. Network calls to external sources are mocked.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.data.db import init_db
from src.data.features import FeatureBuilder
from src.data.ingest import ingest_statsbomb_world_cups
from src.data.repository import MatchRecord, MatchRepository, TeamRepository


class TestDatabaseSchema(unittest.TestCase):
    def test_init_db_creates_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            init_db(db_path)
            with sqlite3.connect(db_path) as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
            expected = {
                "teams", "matches", "xg_events", "elo_history",
                "match_player_stats", "ingestion_log",
            }
            self.assertTrue(expected.issubset(tables))


class TestMatchRepository(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        init_db(self.db_path)
        self.repo = MatchRepository(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_and_retrieve_match(self):
        match = MatchRecord(
            id="ARG-FRA-2022-12-18",
            date="2022-12-18",
            competition="FIFA World Cup",
            season="2022",
            stage="Final",
            home_team_code="ARG",
            away_team_code="FRA",
            home_goals=3,
            away_goals=3,
            home_xg=2.1,
            away_xg=1.8,
            venue="Lusail Stadium",
            neutral=True,
            source="test",
            fetched_at="2024-01-01T00:00:00",
        )
        inserted, updated = self.repo.save_matches([match])
        self.assertEqual(inserted, 1)
        self.assertEqual(updated, 0)

        rows = self.repo.get_matches(team_code="ARG")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].home_goals, 3)
        self.assertEqual(rows[0].away_goals, 3)

    def test_upsert_updates_existing_match(self):
        match = MatchRecord(
            id="ARG-FRA-2022-12-18",
            date="2022-12-18",
            competition="FIFA World Cup",
            season="2022",
            stage="Final",
            home_team_code="ARG",
            away_team_code="FRA",
            home_goals=3,
            away_goals=3,
            home_xg=None,
            away_xg=None,
            venue=None,
            neutral=True,
            source="test",
            fetched_at="2024-01-01T00:00:00",
        )
        self.repo.save_matches([match])
        updated_match = MatchRecord(
            id="ARG-FRA-2022-12-18",
            date="2022-12-18",
            competition="FIFA World Cup",
            season="2022",
            stage="Final",
            home_team_code="ARG",
            away_team_code="FRA",
            home_goals=3,
            away_goals=3,
            home_xg=2.1,
            away_xg=1.8,
            venue=None,
            neutral=True,
            source="test",
            fetched_at="2024-01-01T00:00:00",
        )
        inserted, updated = self.repo.save_matches([updated_match])
        self.assertEqual(inserted, 0)
        self.assertEqual(updated, 1)

        rows = self.repo.get_matches(team_code="ARG")
        self.assertEqual(rows[0].home_xg, 2.1)


class TestFeatureBuilder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        init_db(self.db_path)
        self.repo = MatchRepository(self.db_path)
        self.builder = FeatureBuilder(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _seed_matches(self):
        matches = [
            MatchRecord(
                id="ARG-MEX-2022-11-26",
                date="2022-11-26",
                competition="FIFA World Cup",
                season="2022",
                stage="Group C",
                home_team_code="ARG",
                away_team_code="MEX",
                home_goals=2,
                away_goals=0,
                home_xg=1.9,
                away_xg=0.4,
                venue=None,
                neutral=True,
                source="test",
                fetched_at="2024-01-01T00:00:00",
            ),
            MatchRecord(
                id="ARG-POL-2022-11-30",
                date="2022-11-30",
                competition="FIFA World Cup",
                season="2022",
                stage="Group C",
                home_team_code="ARG",
                away_team_code="POL",
                home_goals=2,
                away_goals=0,
                home_xg=1.5,
                away_xg=0.7,
                venue=None,
                neutral=True,
                source="test",
                fetched_at="2024-01-01T00:00:00",
            ),
            MatchRecord(
                id="ARG-AUS-2022-12-03",
                date="2022-12-03",
                competition="FIFA World Cup",
                season="2022",
                stage="Round of 16",
                home_team_code="ARG",
                away_team_code="AUS",
                home_goals=2,
                away_goals=1,
                home_xg=1.8,
                away_xg=0.9,
                venue=None,
                neutral=True,
                source="test",
                fetched_at="2024-01-01T00:00:00",
            ),
        ]
        self.repo.save_matches(matches)

    def test_build_stats_returns_none_for_missing_team(self):
        stats = self.builder.build_team_stats("ARG", "2022-12-18", min_matches=1)
        self.assertIsNone(stats)

    def test_build_stats_from_real_matches(self):
        self._seed_matches()
        stats = self.builder.build_team_stats("ARG", "2022-12-18", last_n=5, min_matches=2)
        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats.team_code, "ARG")
        self.assertEqual(stats.last_10_wins, 3)
        self.assertEqual(stats.last_10_draws, 0)
        self.assertEqual(stats.last_10_losses, 0)
        self.assertAlmostEqual(stats.xg_per_game, (1.9 + 1.5 + 1.8) / 3, places=2)

    def test_attack_defence_strength(self):
        self._seed_matches()
        result = self.builder.attack_defence_strength("ARG", "2022-12-18", last_n=5)
        self.assertIsNotNone(result)
        assert result is not None
        attack, defence, sample = result
        self.assertGreater(attack, 1.0)
        self.assertLess(defence, 1.0)  # Argentina conceded only 1 goal in 3 matches
        self.assertEqual(sample, 3)


class TestStatsBombIngestion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        init_db(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _mock_fetch(self, path: str):
        if path == "matches/43/3.json":
            return [
                {
                    "match_id": 1,
                    "match_date": "2018-06-30",
                    "home_team": {"home_team_name": "Argentina"},
                    "away_team": {"away_team_name": "France"},
                    "home_score": 3,
                    "away_score": 4,
                    "competition": {"competition_name": "FIFA World Cup"},
                    "season": {"season_name": "2018"},
                    "competition_stage": {"name": "Round of 16"},
                    "stadium": {"name": "Kazan Arena"},
                }
            ]
        if path == "matches/43/106.json":
            return [
                {
                    "match_id": 2,
                    "match_date": "2022-12-18",
                    "home_team": {"home_team_name": "Argentina"},
                    "away_team": {"away_team_name": "France"},
                    "home_score": 3,
                    "away_score": 3,
                    "competition": {"competition_name": "FIFA World Cup"},
                    "season": {"season_name": "2022"},
                    "competition_stage": {"name": "Final"},
                    "stadium": {"name": "Lusail Stadium"},
                }
            ]
        if path == "events/1.json":
            return [
                {
                    "type": {"name": "Shot"},
                    "team": {"name": "Argentina"},
                    "shot": {"statsbomb_xg": 0.15, "outcome": {"name": "Goal"}},
                },
                {
                    "type": {"name": "Shot"},
                    "team": {"name": "France"},
                    "shot": {"statsbomb_xg": 0.10, "outcome": {"name": "Goal"}},
                },
            ]
        if path == "events/2.json":
            return [
                {
                    "type": {"name": "Shot"},
                    "team": {"name": "Argentina"},
                    "shot": {"statsbomb_xg": 0.20, "outcome": {"name": "Goal"}},
                },
                {
                    "type": {"name": "Shot"},
                    "team": {"name": "France"},
                    "shot": {"statsbomb_xg": 0.12, "outcome": {"name": "Goal"}},
                },
            ]
        raise ValueError(f"Unexpected path: {path}")

    @patch("src.data.scrapers.statsbomb._fetch_json")
    def test_ingest_statsbomb_world_cups(self, mock_fetch):
        mock_fetch.side_effect = self._mock_fetch
        result = ingest_statsbomb_world_cups(self.db_path, include_events=True)
        self.assertIn("2022 FIFA World Cup", result)
        self.assertEqual(result["2022 FIFA World Cup"], 1)

        repo = MatchRepository(self.db_path)
        self.assertEqual(repo.count_matches(), 2)
        match = repo.get_matches(team_code="ARG", competition="FIFA World Cup", season="2022")[0]
        self.assertEqual(match.home_goals, 3)
        self.assertEqual(match.away_goals, 3)
        self.assertEqual(match.home_xg, 0.20)
        self.assertEqual(match.away_xg, 0.12)

    @patch("src.data.scrapers.statsbomb._fetch_json")
    def test_ingest_statsbomb_without_events(self, mock_fetch):
        mock_fetch.side_effect = self._mock_fetch
        result = ingest_statsbomb_world_cups(self.db_path, include_events=False)
        repo = MatchRepository(self.db_path)
        match = repo.get_matches(team_code="ARG", competition="FIFA World Cup", season="2022")[0]
        self.assertIsNone(match.home_xg)
        self.assertIsNone(match.away_xg)


class TestTeamRepository(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        init_db(self.db_path)
        self.repo = TeamRepository(self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_and_get_team(self):
        from src.data.repository import TeamRecord

        team = TeamRecord(
            code="ARG", name_en="Argentina", name_zh="阿根廷",
            fifa_ranking=1, elo=2130.0, confederation="CONMEBOL",
        )
        self.repo.save_teams([team])
        fetched = self.repo.get_team("ARG")
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched.name_zh, "阿根廷")
        self.assertEqual(fetched.elo, 2130.0)


class TestEspnScraper(unittest.TestCase):
    def test_parse_event_completed_match(self):
        from src.data.scrapers.espn import _parse_event

        event = {
            "date": "2024-06-09T20:00Z",
            "season": {"slug": "fifa.friendly", "year": "2024"},
            "status": {"type": {"description": "Final"}},
            "competitions": [{
                "type": {"abbreviation": "Friendly"},
                "venue": {"fullName": "MetLife Stadium"},
                "competitors": [
                    {"homeAway": "home", "team": {"displayName": "Argentina"}, "score": "2"},
                    {"homeAway": "away", "team": {"displayName": "Ecuador"}, "score": "0"},
                ],
            }],
        }
        record = _parse_event(event)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.home_team_code, "ARG")
        self.assertEqual(record.away_team_code, "ECU")
        self.assertEqual(record.home_goals, 2)
        self.assertEqual(record.away_goals, 0)
        self.assertEqual(record.source, "espn")

    def test_parse_event_skips_unfinished(self):
        from src.data.scrapers.espn import _parse_event

        event = {"status": {"type": {"description": "Scheduled"}}}
        self.assertIsNone(_parse_event(event))


class TestFbrefScraper(unittest.TestCase):
    @patch("src.data.scrapers.fbref.requests.Session.get")
    def test_fetch_match(self, mock_get):
        from src.data.scrapers.fbref import FbrefScraper, convert_fbref_match

        html = """
        <html>
          <div class="scorebox">
            <div class="scorebox_entity"><a>Argentina</a></div>
            <div class="scorebox_entity"><a>France</a></div>
            <div class="score">3</div>
            <div class="score">3</div>
            <div class="score_xg">2.1</div>
            <div class="score_xg">1.8</div>
          </div>
          <small>Venue: Lusail Stadium</small>
          <span class="venuetime" data-venue-date="2022-12-18"></span>
        </html>
        """
        mock_response = unittest.mock.MagicMock()
        mock_response.text = html
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        scraper = FbrefScraper(delay_seconds=0)
        fbref_match = scraper.fetch_match("https://fbref.com/en/matches/abc/")
        self.assertIsNotNone(fbref_match)
        assert fbref_match is not None
        self.assertEqual(fbref_match.home_team, "Argentina")
        self.assertEqual(fbref_match.home_xg, 2.1)

        record = convert_fbref_match(fbref_match)
        self.assertEqual(record.home_team_code, "ARG")
        self.assertEqual(record.away_team_code, "FRA")
        self.assertEqual(record.home_xg, 2.1)


class TestEloScraper(unittest.TestCase):
    def test_fetch_latest_ratings(self):
        from src.data.scrapers.elo import fetch_latest_ratings

        ratings = dict(fetch_latest_ratings())
        # The bundled snapshot includes the major football nations.
        self.assertIn("ARG", ratings)
        self.assertIn("FRA", ratings)
        self.assertIn("BRA", ratings)
        self.assertGreater(ratings["ARG"], 2000)
        self.assertGreater(ratings["BRA"], 1800)


if __name__ == "__main__":
    unittest.main()
