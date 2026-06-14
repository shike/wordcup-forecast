#!/usr/bin/env python3
"""Predict all World Cup matches playing tonight (Beijing 2026-06-14).

Iterates over the 5 fixtures scheduled to kick off between 12:00 today and
10:00 tomorrow Beijing time, runs the model, and prints a compact summary.
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from src.data.fixtures import fetch_fixtures
from src.utils.config import config
from predict import _resolve_fixture_team


# Tonight's matches (Beijing 2026-06-14 12:00 → 2026-06-15 10:00)
TONIGHT_TEAMS = [
    ("Australia", "Türkiye", "2026-06-14"),
    ("Germany", "Curaçao", "2026-06-15"),
    ("Netherlands", "Japan", "2026-06-15"),
    ("Ivory Coast", "Ecuador", "2026-06-15"),
    ("Sweden", "Tunisia", "2026-06-15"),
]


def main() -> None:
    fx = fetch_fixtures("2026-06-14")
    print(f"\n今晚所有比赛预测（北京时间 {TONIGHT_TEAMS[0][2]} 12:00 起）\n")

    results = []
    for home_zh, away_zh, match_date in TONIGHT_TEAMS:
        # Find the fixture in today's list
        match_fx = next(
            (
                f
                for f in fx
                if f.home_team in (home_zh, home_zh.replace("Türkiye", "Turkey"), home_zh.replace("Curaçao", "Curacao"))
                and f.away_team in (away_zh, away_zh.replace("Curaçao", "Curacao"), away_zh.replace("Türkiye", "Turkey"))
            ),
            None,
        )
        # Fall back: search by code
        if not match_fx:
            for f in fx:
                if (
                    (f.home_code == "AUS" and f.away_code == "TUR" and home_zh == "Australia")
                    or (f.home_code == "GER" and f.away_code == "CUW" and home_zh == "Germany")
                    or (f.home_code == "NED" and f.away_code == "JPN" and home_zh == "Netherlands")
                    or (f.home_code == "CIV" and f.away_code == "ECU" and home_zh == "Ivory Coast")
                    or (f.home_code == "SWE" and f.away_code == "TUN" and home_zh == "Sweden")
                ):
                    match_fx = f
                    break

        if not match_fx:
            print(f"⚠️  {home_zh} vs {away_zh}: 找不到 fixture")
            continue

        home_team = _resolve_fixture_team(match_fx.home_team, code=match_fx.home_code)
        away_team = _resolve_fixture_team(match_fx.away_team, code=match_fx.away_code)
        if not home_team or not away_team:
            print(f"⚠️  {home_zh} vs {away_zh}: teams not in seed database")
            continue

        from src.data.fixtures import to_beijing, venue_chinese
        bj = to_beijing(match_fx.kickoff_utc)
        kickoff_str = f"{bj[:10]} {bj[11:]} 北京时间" if bj else "TBD"
        venue_str = venue_chinese(match_fx.venue) or match_fx.venue or "TBD"

        from src.pipeline import run_prediction

        try:
            result = run_prediction(
                team_a=home_team,
                team_b=away_team,
                match_date=match_date,
                stage="group",
                venue=venue_str,
                lang="zh",
                simulations=10_000,
            )
        except Exception as exc:
            print(f"❌  {home_zh} vs {away_zh}: 预测失败 — {exc}")
            continue

        probs = result.model_probs.win_draw_loss
        eg = result.model_probs.expected_goals
        # Use the most likely score that matches the consensus pick
        score = result.monte_carlo.predicted_score_for(result.recommended_pick)
        score_prob = result.monte_carlo.distribution.get(score, 0.0)
        confidence_zh = {"high": "高", "medium": "中", "low": "低"}[result.confidence]
        pick_zh = (
            home_team.name_zh if result.recommended_pick == "A"
            else away_team.name_zh if result.recommended_pick == "B"
            else "平局"
        )
        home_xg = round(result.team_a_stats.xg_per_game, 2)
        away_xg = round(result.team_b_stats.xg_per_game, 2)

        # Top 5 scores
        top5 = sorted(result.monte_carlo.distribution.items(), key=lambda kv: -kv[1])[:5]

        print(f"🏟️  {home_team.name_zh} vs {away_team.name_zh}")
        print(f"    ⏰ {kickoff_str}  ·  📍 {venue_str}")
        print(f"    胜 {probs[0]:.1%}  |  平 {probs[1]:.1%}  |  负 {probs[2]:.1%}")
        print(f"    推荐: {pick_zh}  ·  比分: {score} ({score_prob:.1%})  ·  信心: {confidence_zh}")
        print(f"    xG 期望: {eg[0]:.2f} - {eg[1]:.2f}  ·  近况 xG/场: {home_xg} - {away_xg}")
        print(f"    Top 5 比分: {', '.join(f'{s}({p*100:.1f}%)' for s, p in top5)}")
        print()
        results.append((home_team.name_zh, away_team.name_zh, score, probs, pick_zh))

    print("=" * 60)
    print("今晚预测汇总:")
    for h, a, score, probs, pick in results:
        print(f"  {h} vs {a}  →  {score}  ·  {pick}  ({probs[0]:.0%}/{probs[1]:.0%}/{probs[2]:.0%})")


if __name__ == "__main__":
    main()
