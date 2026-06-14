#!/usr/bin/env python3
"""Hourly odds movement monitor.

Pulls DraftKings odds from ESPN every hour and appends the snapshot to
a JSON Lines log at 缓存/odds_movement.jsonl. Downstream consumers
(plot.py, PPT rebuilding) can read this to track line moves.

Usage:
    python scripts/odds_monitor.py --date 2026-06-14
    python scripts/odds_monitor.py --date 2026-06-14 --append  # append to log
    python scripts/odds_monitor.py --date 2026-06-14 --diff   # show diff vs last
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.data.scrapers.espn_odds import (
    american_to_implied,
    fetch_odds,
    market_probs,
)
from src.utils.config import config


def fetch_snapshot(date_str: str) -> dict:
    """Fetch current odds and return a timestamped snapshot."""
    odds_map = fetch_odds(date_str)
    snapshot: dict = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "date": date_str,
        "events": {},
    }
    for eid, o in odds_map.items():
        probs = market_probs(o)
        snapshot["events"][eid] = {
            "home_moneyline": o.home,
            "draw_moneyline": o.draw,
            "away_moneyline": o.away,
            "over_under": o.over_under,
            "over_odds": o.over_odds,
            "under_odds": o.under_odds,
            "p_home": probs[0] if probs else None,
            "p_draw": probs[1] if probs else None,
            "p_away": probs[2] if probs else None,
            "expected_total": probs[3] if probs else None,
        }
    return snapshot


def append_snapshot(snapshot: dict) -> None:
    """Append a snapshot to the JSON Lines log."""
    log = Path("缓存/odds_movement.jsonl")
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    print(f"Appended snapshot to {log}")


def diff_vs_last(snapshot: dict) -> dict:
    """Compute a diff against the previous snapshot in the log."""
    log = Path("缓存/odds_movement.jsonl")
    if not log.exists():
        return {}
    lines = log.read_text(encoding="utf-8").strip().split("\n")
    if len(lines) < 1:
        return {}
    try:
        prev = json.loads(lines[-1])
    except json.JSONDecodeError:
        return {}
    diff: dict = {}
    for eid, e in snapshot.get("events", {}).items():
        prev_e = prev.get("events", {}).get(eid, {})
        deltas = {}
        for k in ("home_moneyline", "draw_moneyline", "away_moneyline",
                  "over_odds", "under_odds", "over_under"):
            if k in e and e[k] != prev_e.get(k):
                deltas[k] = {"old": prev_e.get(k), "new": e[k]}
        for k in ("p_home", "p_draw", "p_away", "expected_total"):
            if e.get(k) and prev_e.get(k) is not None:
                delta = round(e[k] - prev_e[k], 3)
                if abs(delta) >= 0.005:
                    deltas[k] = {"old": round(prev_e[k], 3), "new": round(e[k], 3), "delta": delta}
        if deltas:
            diff[eid] = deltas
    return diff


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", default="20260614", help="YYYYMMDD")
    p.add_argument("--append", action="store_true", help="Append to JSONL log")
    p.add_argument("--diff", action="store_true", help="Show diff vs last snapshot")
    p.add_argument("--once", action="store_true", help="Run once and exit (no daemon)")
    args = p.parse_args()

    snapshot = fetch_snapshot(args.date)
    if args.diff:
        d = diff_vs_last(snapshot)
        if d:
            print(json.dumps(d, ensure_ascii=False, indent=2))
        else:
            print("No line moves since last snapshot.")
    else:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    if args.append:
        append_snapshot(snapshot)


if __name__ == "__main__":
    main()
