"""StatsBomb event-level feature extractor.

Reads StatsBomb Open Data event JSON files (cached locally) and produces:

  1. Per-player per-match stats inserted into `match_player_stats`.
  2. Per-shot records inserted into `xg_events` (using StatsBomb's official
     statsbomb_xg field).
  3. Team-level match summary that we use to backfill possession, pressing,
     set-piece share into the `matches` table.

StatsBomb events have no yellow/red card field for the 2018/2022 World Cups,
so cards_yellow / cards_red remain 0 here. Possession is derived from the
`possession` counter (which group-of-events share the same id) and the
`possession_team` field.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from loguru import logger

from src.data.db import get_connection
from src.data.scrapers.statsbomb import _team_code_from_statsbomb_name
from src.utils.config import config


CACHE_DIR = config.cache_dir / "statsbomb"
MATCH_FILES = {
    (43, 3): "matches_43_3.json",     # 2018 FIFA World Cup
    (43, 106): "matches_43_106.json", # 2022 FIFA World Cup
}


@dataclass
class PlayerMatchStats:
    team_code: str
    player_name: str
    minutes: int = 0
    goals: int = 0
    assists: int = 0
    xg: float = 0.0
    shots: int = 0
    shots_on_target: int = 0
    key_passes: int = 0
    tackles: int = 0
    interceptions: int = 0
    clearances: int = 0
    pressures: int = 0
    fouls_committed: int = 0
    fouls_won: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    ball_recoveries: int = 0
    dribbles_completed: int = 0


@dataclass
class TeamMatchSummary:
    team_code: str
    passes_attempted: int = 0
    passes_completed: int = 0
    pressure_count: int = 0
    opponent_possessions: int = 0
    possession_seconds: float = 0.0
    set_piece_goals: int = 0
    set_piece_attempts: int = 0
    shots: int = 0
    shots_on_target: int = 0
    corners: int = 0
    fouls: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    # Per-period possession durations: possession_id -> (team, start_sec, end_sec)
    possessions: list[tuple[str, str, float, float]] = field(default_factory=list)


# A shot is "on target" if the keeper couldn't catch it cleanly before a goal
# or it was headed for the goal line.
_ON_TARGET_OUTCOMES = {
    "Goal",
    "Saved",
    "Saved to Post",
    "Saved Off Target",
}

_SET_PIECE_PATTERNS = {
    "From Free Kick",
    "From Corner",
    "From Throw In",
    "From Goal Kick",
    "From Keeper",
}

_CORNER_LIKE_PATTERNS = {
    "From Corner",
    "From Free Kick",
}


def _load_match_index() -> dict[int, dict]:
    """Index every StatsBomb match id -> raw match dict."""
    index: dict[int, dict] = {}
    for (comp_id, season_id), filename in MATCH_FILES.items():
        path = CACHE_DIR / filename
        if not path.exists():
            logger.warning(f"Missing match index: {path}")
            continue
        with open(path, encoding="utf-8") as f:
            for m in json.load(f):
                index[m["match_id"]] = m
    return index


def _ensure_events_cached(match_ids: list[int]) -> None:
    """Download missing event files (best effort, no network if already cached)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for mid in match_ids:
        local = CACHE_DIR / f"events_{mid}.json"
        if local.exists():
            continue
        url = f"https://raw.githubusercontent.com/statsbomb/open-data/master/data/events/{mid}.json"
        try:
            import requests

            r = requests.get(url, timeout=30)
            r.raise_for_status()
            local.write_bytes(r.content)
            logger.info(f"  Downloaded events for {mid}")
        except Exception as exc:
            logger.debug(f"  Skipping {mid}: {exc}")


def _iter_events(match_ids: list[int]) -> Iterator[tuple[int, dict]]:
    for mid in match_ids:
        path = CACHE_DIR / f"events_{mid}.json"
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for ev in json.load(f):
                yield mid, ev


def _team_code_for_event(event: dict, team_mapping: dict[str, str]) -> str | None:
    """Map event's possession_team to project code (if possible)."""
    team = event.get("team") or event.get("possession_team") or {}
    name = team.get("name")
    if not name:
        return None
    return _team_code_from_statsbomb_name(name, team_mapping)


def _team_display_name(match: dict, side: str) -> str:
    return match[f"{side}_team"][f"{side}_team_name"]


def _summary_for_event_type(
    event: dict,
    player_stats: dict[tuple[str, str], PlayerMatchStats],
    team_summary: dict[str, TeamMatchSummary],
    team_code: str,
    minutes_for_player: dict[str, int],
) -> None:
    """Update team + player stats counters for one event."""
    type_name = event["type"]["name"]
    player_name = event.get("player", {}).get("name") if event.get("player") else None

    if player_name and team_code:
        key = (team_code, player_name)
        ps = player_stats.setdefault(key, PlayerMatchStats(team_code=team_code, player_name=player_name))
    else:
        ps = None

    ts = team_summary.setdefault(team_code, TeamMatchSummary(team_code=team_code))

    if type_name == "Shot" and "shot" in event:
        shot = event["shot"]
        ts.shots += 1
        if "statsbomb_xg" in shot:
            xg = float(shot["statsbomb_xg"]) or 0.0
            if ps:
                ps.xg += xg
                ps.shots += 1
        outcome = shot.get("outcome", {}).get("name", "")
        if outcome == "Goal":
            if ps:
                ps.goals += 1
            if ps and event.get("play_pattern", {}).get("name") in _SET_PIECE_PATTERNS:
                ts.set_piece_goals += 1
        if outcome in _ON_TARGET_OUTCOMES:
            ts.shots_on_target += 1
            if ps:
                ps.shots_on_target += 1
        if event.get("play_pattern", {}).get("name") in _SET_PIECE_PATTERNS:
            ts.set_piece_attempts += 1
        # Detect corners: from corner → set_piece, we count separately
        if event.get("play_pattern", {}).get("name") == "From Corner":
            ts.corners += 1

    elif type_name == "Pass" and "pass" in event:
        pass_obj = event["pass"]
        ts.passes_attempted += 1
        if "outcome" not in pass_obj:
            ts.passes_completed += 1
        if "shot_assist" in pass_obj or "goal_assist" in pass_obj:
            if ps:
                ps.key_passes += 1
                if "goal_assist" in pass_obj:
                    ps.assists += 1

    elif type_name == "Pressure":
        ts.pressure_count += 1
        if ps:
            ps.pressures += 1

    elif type_name == "Foul Committed":
        ts.fouls += 1
        if ps:
            ps.fouls_committed += 1

    elif type_name == "Foul Won":
        if ps:
            ps.fouls_won += 1

    elif type_name == "Duel" and "duel" in event:
        if event["duel"].get("type", {}).get("name") == "Tackle":
            outcome = event["duel"].get("outcome", {}).get("name", "")
            # "Won" or "Success" or similar — count if we won
            if outcome in ("Won", "Success", "Success In Play", "Success Out"):
                if ps:
                    ps.tackles += 1

    elif type_name == "Interception":
        if ps:
            ps.interceptions += 1

    elif type_name == "Clearance":
        if ps:
            ps.clearances += 1

    elif type_name == "Ball Recovery":
        if ps:
            ps.ball_recoveries += 1

    elif type_name == "Dribble" and "dribble" in event:
        outcome = event["dribble"].get("outcome", {}).get("name", "")
        if outcome == "Complete":
            if ps:
                ps.dribbles_completed += 1


def _build_possession_durations(events: list[dict]) -> dict[tuple[str, str], float]:
    """Compute per-possession duration in seconds, keyed by (possession_team, possession_id)."""
    # Sort events by index to walk chronologically.
    def _period_id(e: dict) -> int:
        p = e.get("period", 1)
        return p.get("id", 1) if isinstance(p, dict) else p

    events = sorted(events, key=lambda e: (_period_id(e), e.get("index", 0)))
    durations: dict[tuple[str, str], float] = {}
    for e in events:
        poss = e.get("possession")
        poss_team = e.get("possession_team")
        if poss is None or not poss_team:
            continue
        key = (poss_team["name"], str(poss))
        ts = _event_seconds(e)
        if ts is None:
            continue
        if key not in durations:
            durations[key] = (ts, ts)
        else:
            start, end = durations[key]
            durations[key] = (min(start, ts), max(end, ts))
    # Convert pairs to single float
    return {k: v[1] - v[0] for k, v in durations.items()}


def _event_seconds(event: dict) -> float | None:
    period_raw = event.get("period", 1)
    if isinstance(period_raw, dict):
        period = period_raw.get("id", 1)
    else:
        period = period_raw
    minute = event.get("minute", 0) or 0
    second = event.get("second", 0) or 0
    base = (period - 1) * 45 * 60
    return base + minute * 60 + second


def extract_match_features(
    match_id: int,
    match: dict,
    team_mapping: dict[str, str],
) -> tuple[str, list[tuple], list[tuple], list[dict]]:
    """Process one match and return (canonical_id, player_stats_rows, xg_event_rows, match_updates)."""
    path = CACHE_DIR / f"events_{match_id}.json"
    if not path.exists():
        return "", [], [], []
    with open(path, encoding="utf-8") as f:
        events: list[dict] = json.load(f)

    home_code = _team_code_from_statsbomb_name(_team_display_name(match, "home"), team_mapping)
    away_code = _team_code_from_statsbomb_name(_team_display_name(match, "away"), team_mapping)
    if not home_code or not away_code:
        return "", [], [], []

    # Use the same ID format as statsbomb.py loader so FKs line up.
    canonical_id = f"{home_code}-{away_code}-{match['match_date']}"

    player_stats: dict[tuple[str, str], PlayerMatchStats] = {}
    team_summary: dict[str, TeamMatchSummary] = {}

    for ev in events:
        team_code = _team_code_for_event(ev, team_mapping)
        if not team_code:
            continue
        _summary_for_event_type(ev, player_stats, team_summary, team_code, {})

    # Estimate minutes played: from first to last event for that player
    minutes_played: dict[tuple[str, str], int] = {}
    sorted_events = sorted(events, key=lambda e: e.get("index", 0))
    for ev in sorted_events:
        team_code = _team_code_for_event(ev, team_mapping)
        player_name = ev.get("player", {}).get("name") if ev.get("player") else None
        if not team_code or not player_name:
            continue
        ts = _event_seconds(ev)
        if ts is None:
            continue
        key = (team_code, player_name)
        if key not in minutes_played:
            minutes_played[key] = int(ts // 60)
        else:
            minutes_played[key] = max(minutes_played[key], int(ts // 60))

    # Build rows
    player_rows: list[tuple] = []
    for (team_code, player_name), ps in player_stats.items():
        ps.minutes = minutes_played.get((team_code, player_name), ps.minutes)
        player_rows.append((
            canonical_id,
            ps.team_code,
            ps.player_name,
            ps.minutes,
            ps.goals,
            ps.assists,
            round(ps.xg, 3),
            0.0,  # xga
            ps.shots,
            ps.shots_on_target,
            ps.key_passes,
            ps.tackles,
            ps.interceptions,
            ps.yellow_cards,
            ps.red_cards,
        ))

    # Build xG events rows from shots
    xg_rows: list[tuple] = []
    for ev in events:
        if ev.get("type", {}).get("name") != "Shot":
            continue
        if "statsbomb_xg" not in ev.get("shot", {}):
            continue
        team_code = _team_code_for_event(ev, team_mapping)
        if not team_code:
            continue
        player_name = ev.get("player", {}).get("name", "Unknown")
        xg_rows.append((
            canonical_id,
            team_code,
            player_name,
            float(ev["shot"]["statsbomb_xg"]),
            ev.get("minute", 0),
            ev.get("shot", {}).get("body_part", {}).get("name"),
            ev.get("shot", {}).get("outcome", {}).get("name"),
        ))

    # Compute possession summary
    poss_durations = _build_possession_durations(events)
    for key, duration in poss_durations.items():
        team_name = key[0]
        code = _team_code_from_statsbomb_name(team_name, team_mapping)
        if code and code in team_summary:
            team_summary[code].possession_seconds = duration

    possession_by_code: dict[str, float] = {}
    for key, duration in poss_durations.items():
        team_name = key[0]
        code = _team_code_from_statsbomb_name(team_name, team_mapping)
        if code:
            possession_by_code[code] = possession_by_code.get(code, 0.0) + duration

    updates: list[dict] = []
    if home_code and away_code:
        total = sum(possession_by_code.values()) or 1.0
        for code, ts in team_summary.items():
            pass_pct = (
                ts.passes_completed / ts.passes_attempted
                if ts.passes_attempted > 0
                else 0.0
            )
            updates.append({
                "team": code,
                "possession_pct": round(possession_by_code.get(code, 0.0) / total, 3),
                "pressures": ts.pressure_count,
                "pass_pct": round(pass_pct, 3),
                "set_piece_goals": ts.set_piece_goals,
                "set_piece_attempts": ts.set_piece_attempts,
                "shots": ts.shots,
                "shots_on_target": ts.shots_on_target,
                "corners": ts.corners,
                "fouls": ts.fouls,
                "yellow_cards": ts.yellow_cards,
                "red_cards": ts.red_cards,
            })
    return canonical_id, player_rows, xg_rows, updates


def persist_player_stats(
    match_id: int,
    rows: list[tuple],
    db_path: Path | None = None,
) -> int:
    if not rows:
        return 0
    with get_connection(db_path) as conn:
        for row in rows:
            conn.execute(
                """
                INSERT OR REPLACE INTO match_player_stats (
                    match_id, team_code, player_name, minutes, goals, assists,
                    xg, xga, shots, shots_on_target, key_passes, tackles,
                    interceptions, cards_yellow, cards_red
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
        conn.commit()
    return len(rows)


def persist_xg_events(
    match_id: int,
    rows: list[tuple],
    db_path: Path | None = None,
) -> int:
    if not rows:
        return 0
    with get_connection(db_path) as conn:
        for row in rows:
            # Skip duplicates if rerun: delete same match_id+team+player+minute first
            conn.execute(
                "DELETE FROM xg_events WHERE match_id = ? AND team_code = ? AND player_name = ? AND minute = ?",
                (row[0], row[1], row[2], row[4]),
            )
            conn.execute(
                """
                INSERT INTO xg_events (match_id, team_code, player_name, xg, minute, shot_type, result)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
        conn.commit()
    return len(rows)


def backfill_match_summaries(
    updates: list[dict],
    canonical_id: str,
    db_path: Path | None = None,
) -> int:
    """Update the matches table with possession, fouls, cards, corners.

    We do not overwrite home_goals / away_goals / home_xg / away_xg because
    those are authoritative from StatsBomb. We just add match-level defensive
    summary fields via INSERT-only side tables — but the schema doesn't have
    a place for these on the matches row, so we only log them for now.
    """
    if not updates:
        return 0
    # Persist to a side JSON file for future use by FeatureBuilder.
    # The file is keyed by the canonical ID (HOME-AWAY-YYYY-MM-DD) so
    # `match_player_stats.match_id` and this file can be joined.
    safe_id = canonical_id.replace("/", "_")
    log_path = config.api_cache / f"statsbomb_match_summary_{safe_id}.json"
    log_path.write_text(
        json.dumps({"match_id": canonical_id, "teams": updates}, ensure_ascii=False),
        encoding="utf-8",
    )
    return len(updates)


def run_all(
    db_path: Path | None = None,
    download_missing: bool = True,
) -> dict[str, int]:
    """Run feature extraction across all cached + downloadable StatsBomb matches.

    Returns a summary dict.
    """
    match_index = _load_match_index()
    if not match_index:
        logger.error("No StatsBomb match index found")
        return {"player_rows": 0, "xg_rows": 0, "summaries": 0}

    match_ids = sorted(match_index.keys())
    logger.info(f"StatsBomb feature extraction: {len(match_ids)} matches")
    if download_missing:
        _ensure_events_cached(match_ids)

    from src.data.scrapers._team_names import load_project_mapping

    team_mapping = load_project_mapping()

    total_player_rows = 0
    total_xg_rows = 0
    total_summaries = 0

    for mid in match_ids:
        match = match_index[mid]
        canonical_id, player_rows, xg_rows, summaries = extract_match_features(
            mid, match, team_mapping
        )
        if not canonical_id:
            continue
        total_player_rows += persist_player_stats(canonical_id, player_rows, db_path)
        total_xg_rows += persist_xg_events(canonical_id, xg_rows, db_path)
        total_summaries += backfill_match_summaries(summaries, canonical_id, db_path)

    summary = {
        "matches_processed": len(match_ids),
        "player_rows": total_player_rows,
        "xg_rows": total_xg_rows,
        "summaries": total_summaries,
    }
    logger.info(
        f"StatsBomb features: {total_player_rows} player rows, "
        f"{total_xg_rows} xG events, {total_summaries} match summaries"
    )
    return summary


if __name__ == "__main__":
    from src.data.db import init_db

    init_db()
    result = run_all()
    print("Feature extraction result:", result)
