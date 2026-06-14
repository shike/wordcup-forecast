"""Feature builder: derive prediction inputs from real warehouse data.

All numbers come from the SQLite data warehouse. If a team has no real matches,
the builder returns None so the caller can decide whether to fall back to ELO
or abort. There is no silent synthetic fallback.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.data.db import get_connection
from src.data.repository import MatchRepository
from src.utils.models import TeamStats


@dataclass(frozen=True)
class TeamForm:
    matches_played: int
    wins: int
    draws: int
    losses: int
    goals_for: float
    goals_against: float
    xg_for: float
    xg_against: float
    clean_sheets: int
    shots: float
    shots_on_target: float
    key_passes: float
    tackles: float
    interceptions: float
    cards_yellow: float
    cards_red: float
    possession_avg: float | None
    pressures: float = 0.0
    pass_pct: float = 0.0
    set_piece_goals: int = 0
    set_piece_attempts: int = 0
    # Time-decay-weighted rate stats (recompute with half-life 720d)
    weighted_xg_for: float = 0.0
    weighted_xg_against: float = 0.0
    weighted_gf: float = 0.0
    weighted_ga: float = 0.0


class FeatureBuilder:
    """Build team statistics from real match records."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._repo = MatchRepository(db_path)
        self._db_path = db_path

    def build_team_stats(
        self,
        team_code: str,
        reference_date: str,
        last_n: int = 10,
        min_matches: int = 3,
    ) -> TeamStats | None:
        """Build TeamStats from matches strictly before reference_date.

        Returns None if the team has fewer than min_matches real matches.
        Possession data is not currently ingested, so possession_avg stays
        None. Callers must not assume a default value.
        """
        matches = self._repo.get_matches(
            team_code=team_code, before=reference_date, limit=last_n
        )
        if len(matches) < min_matches:
            return None

        if not matches:
            return None

        # Use the time-decay-weighted aggregator (half-life 720 days).
        form = self._aggregate_form_weighted(team_code, matches, half_life_days=720.0)

        gp = form.matches_played
        set_piece_pct = (
            round(form.set_piece_goals / form.set_piece_attempts, 2)
            if form.set_piece_attempts > 0
            else 0.0
        )
        # pressing_intensity: pressures per opponent possession attempt.
        # Approximated by raw pressures per game; in [0,1] for World Cup.
        pressing = min(1.0, form.pressures / (gp * 60)) if gp else 0.0
        return TeamStats(
            team_code=team_code,
            last_10_wins=form.wins,
            last_10_draws=form.draws,
            last_10_losses=form.losses,
            goals_per_game=round(form.weighted_gf, 2),
            conceded_per_game=round(form.weighted_ga, 2),
            xg_per_game=round(form.weighted_xg_for, 2),
            xga_per_game=round(form.weighted_xg_against, 2),
            clean_sheet_rate=round(form.clean_sheets / gp, 2),
            key_passes_per_game=round(form.key_passes / gp, 1),
            shot_accuracy=round(
                (form.shots_on_target / form.shots) if form.shots > 0 else 0.0, 2
            ),
            tackles_per_game=round(form.tackles / gp, 1),
            interceptions_per_game=round(form.interceptions / gp, 1),
            avg_player_rating=0.0,  # requires external player-rating source
            starter_strength=0.0,
            bench_strength=0.0,
            cards_per_game=round((form.cards_yellow + form.cards_red) / gp, 2),
            fouls_per_game=0.0,  # fouls are not in the base schema
            days_since_last_match=self._days_since(reference_date, matches[0].date),
            matches_in_last_7_days=self._matches_in_window(matches, reference_date, days=7),
            set_piece_goals_pct=set_piece_pct,
            possession_avg=form.possession_avg,
            pressing_intensity=pressing,
        )

    def attack_defence_strength(
        self,
        team_code: str,
        reference_date: str,
        last_n: int = 10,
        league_mean: float = 1.27,
    ) -> tuple[float, float, int] | None:
        """Return (attack_strength, defence_weakness, sample_size).

        Prefers xG when available; falls back to actual goals when xG has not
        been ingested (e.g. StatsBomb without events). This keeps the model
        usable while still being honest about data quality.
        """
        matches = self._repo.get_matches(
            team_code=team_code, before=reference_date, limit=last_n
        )
        if not matches:
            return None

        form = self._aggregate_form(team_code, matches)
        gp = form.matches_played

        # Use xG when at least one match has it; otherwise fall back to goals.
        has_xg = form.xg_for > 0 or form.xg_against > 0
        attack_metric = form.xg_for if has_xg else form.goals_for
        defence_metric = form.xg_against if has_xg else form.goals_against

        attack = round((attack_metric / gp) / league_mean, 3)
        defence = round((defence_metric / gp) / league_mean, 3) if defence_metric > 0 else 1.0
        return attack, defence, gp

    def _aggregate_form(self, team_code: str, matches: list) -> TeamForm:
        """Default aggregation: equal weight per match.

        Use `_aggregate_form_weighted` for time-decay-aware aggregation.
        """
        return self._aggregate_form_weighted(team_code, matches, half_life_days=None)

    def _aggregate_form_weighted(
        self,
        team_code: str,
        matches: list,
        half_life_days: float | None = 720.0,
    ) -> TeamForm:
        """Aggregate recent matches with optional time-decay weights.

        Args:
            half_life_days: Time (in days) for a match's weight to halve
                relative to the most recent match. None = equal weight.

        Half-life of 720 days (~2 years) means a match 2 years old
        contributes half as much as a match today; a 4-year-old match
        contributes 25% of a fresh match's weight.
        """
        from datetime import date as _date

        if not matches:
            return TeamForm(
                matches_played=0, wins=0, draws=0, losses=0,
                goals_for=0.0, goals_against=0.0, xg_for=0.0, xg_against=0.0,
                clean_sheets=0, shots=0.0, shots_on_target=0.0,
                key_passes=0.0, tackles=0.0, interceptions=0.0,
                cards_yellow=0.0, cards_red=0.0, possession_avg=None,
                pressures=0.0, pass_pct=0.0, set_piece_goals=0,
                set_piece_attempts=0,
            )

        # Most recent match date is the reference point
        most_recent = max(_date.fromisoformat(m.date) for m in matches)

        def _weight(match_date_str: str) -> float:
            if half_life_days is None or half_life_days <= 0:
                return 1.0
            d = _date.fromisoformat(match_date_str)
            days_old = (most_recent - d).days
            return 0.5 ** (days_old / half_life_days)

        wins = draws = losses = clean_sheets = 0
        gf = ga = xgf = xga = 0.0
        shots = sot = kp = tackles = inters = cy = cr = 0.0
        possession_sum = 0.0
        possession_count = 0
        pressures_sum = 0.0
        pass_pct_sum = 0.0
        pass_pct_count = 0
        set_piece_goals = 0
        set_piece_attempts = 0
        # weighted versions
        gf_w = ga_w = xgf_w = xga_w = 0.0
        wsum = 0.0

        for m in matches:
            w = _weight(m.date)
            wsum += w
            is_home = m.home_team_code == team_code
            team_goals = m.home_goals if is_home else m.away_goals
            opp_goals = m.away_goals if is_home else m.home_goals
            team_xg = m.home_xg if is_home else m.away_xg
            opp_xg = m.away_xg if is_home else m.home_xg

            if team_goals is None or opp_goals is None:
                continue

            if team_goals > opp_goals:
                wins += 1
            elif team_goals == opp_goals:
                draws += 1
            else:
                losses += 1

            if opp_goals == 0:
                clean_sheets += 1

            # Use unweighted totals for count-based fields, weighted for
            # rate-based fields (goals/xG per game).
            gf += team_goals
            ga += opp_goals
            xgf += team_xg or 0.0
            xga += opp_xg or 0.0
            gf_w += team_goals * w
            ga_w += opp_goals * w
            xgf_w += (team_xg or 0.0) * w
            xga_w += (opp_xg or 0.0) * w

            stats = self._fetch_player_stats(m.id, team_code)
            for s in stats:
                shots += s.get("shots", 0)
                sot += s.get("shots_on_target", 0)
                kp += s.get("key_passes", 0)
                tackles += s.get("tackles", 0)
                inters += s.get("interceptions", 0)
                cy += s.get("cards_yellow", 0)
                cr += s.get("cards_red", 0)

            summary = self._fetch_match_summary(m.id, team_code)
            if summary:
                poss = summary.get("possession_pct")
                if poss is not None:
                    possession_sum += poss * w
                    possession_count += 1
                pressures_sum += summary.get("pressures", 0)
                pass_pct = summary.get("pass_pct")
                if pass_pct:
                    pass_pct_sum += pass_pct * w
                    pass_pct_count += 1
                set_piece_goals += summary.get("set_piece_goals", 0) or 0
                set_piece_attempts += summary.get("set_piece_attempts", 0) or 0

        gp = len(matches)
        effective_gp = max(1.0, wsum)
        possession_avg = (
            round(possession_sum / wsum, 3) if wsum and possession_count else None
        )
        pressures_avg = round(pressures_sum / gp, 1) if gp else 0.0
        pass_pct_avg = (
            round(pass_pct_sum / wsum, 3) if wsum and pass_pct_count else 0.0
        )
        # For the legacy totals (unweighted), keep the existing semantics
        # so the schema fields stay comparable.
        return TeamForm(
            matches_played=gp,
            wins=wins,
            draws=draws,
            losses=losses,
            goals_for=gf,
            goals_against=ga,
            xg_for=xgf,
            xg_against=xga,
            clean_sheets=clean_sheets,
            shots=shots,
            shots_on_target=sot,
            key_passes=kp,
            tackles=tackles,
            interceptions=inters,
            cards_yellow=cy,
            cards_red=cr,
            possession_avg=possession_avg,
            pressures=pressures_avg,
            pass_pct=pass_pct_avg,
            set_piece_goals=set_piece_goals,
            set_piece_attempts=set_piece_attempts,
            weighted_xg_for=xgf_w / effective_gp,
            weighted_xg_against=xga_w / effective_gp,
            weighted_gf=gf_w / effective_gp,
            weighted_ga=ga_w / effective_gp,
        )

    def _fetch_player_stats(self, match_id: str, team_code: str) -> list[dict]:
        with get_connection(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT shots, shots_on_target, key_passes, tackles,
                       interceptions, cards_yellow, cards_red
                FROM match_player_stats
                WHERE match_id = ? AND team_code = ?
                """,
                (match_id, team_code),
            ).fetchall()
            return [dict(row) for row in rows]

    def _fetch_match_summary(self, match_id: str, team_code: str) -> dict | None:
        """Load the StatsBomb match summary sidecar JSON if present.

        Returns a dict with possession_pct, pressures, pass_pct,
        set_piece_goals, set_piece_attempts, corners, fouls, etc., or
        None when no summary has been written for the match.
        """
        from src.utils.config import config

        path = config.api_cache / f"statsbomb_match_summary_{match_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        for entry in data.get("teams", []):
            if entry.get("team") == team_code:
                return entry
        return None

    @staticmethod
    def _days_since(reference_date: str, last_match_date: str) -> int:
        from datetime import date

        try:
            d_ref = date.fromisoformat(reference_date)
            d_last = date.fromisoformat(last_match_date)
            return max(0, (d_ref - d_last).days)
        except ValueError:
            return 7

    @staticmethod
    def _matches_in_window(matches: list, reference_date: str, days: int) -> int:
        from datetime import date

        try:
            d_ref = date.fromisoformat(reference_date)
        except ValueError:
            return 0
        cutoff = d_ref.toordinal() - days
        return sum(
            1
            for m in matches
            if date.fromisoformat(m.date).toordinal() >= cutoff
        )
