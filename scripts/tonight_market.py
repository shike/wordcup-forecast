#!/usr/bin/env python3
"""Tonight's predictions, driven by real DraftKings odds from ESPN.

For matches with odds (4 of the 5 tonight), uses the market-implied
1X2 probabilities, expected total, and the O/U line. For the live
match (AUS-TUR, in progress), falls back to the model.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from loguru import logger

from src.data.fixtures import fetch_fixtures
from src.data.scrapers.espn_odds import (
    american_to_implied,
    fetch_odds,
    market_probs,
)
from src.predict.market import _poisson_pmf, MarketMatch, predict_match


def _poisson_lambdas_from_elo(elo_h: float, elo_a: float) -> tuple[float, float]:
    """Fallback: ELO-driven lambdas when no market odds are available."""
    # 1.27 is the World Cup historical mean
    base = 1.27
    # Each ELO 100 above opponent → +0.13 goals
    diff = (elo_h - elo_a) / 100.0
    lam_h = max(0.5, base + 0.4 * diff)
    lam_a = max(0.5, base - 0.4 * diff)
    return lam_h, lam_a


def _elo_for(team_code: str, default: int = 1800) -> int:
    """Quick ELO lookup (could pull from DB but keep it simple here)."""
    # Known top-32 ELOs (rounded to 10) — keeps the script self-contained.
    table = {
        "GER": 1960, "CUW": 1620, "NED": 2030, "JPN": 1910, "CIV": 1790,
        "ECU": 1840, "SWE": 1820, "TUN": 1730, "AUS": 1810, "TUR": 1840,
        "ARG": 2130, "BRA": 2030, "ESP": 1980, "FRA": 2090, "ENG": 2010,
        "ITA": 1900, "POR": 1990, "MEX": 1880, "USA": 1860, "URU": 1900,
    }
    return table.get(team_code, default)


def _build_score_matrix(lam_h: float, lam_a: float, max_goals: int = 10) -> list[list[float]]:
    matrix = [[_poisson_pmf(lam_h, i) * _poisson_pmf(lam_a, j) for j in range(max_goals + 1)] for i in range(max_goals + 1)]
    s = sum(sum(row) for row in matrix)
    return [[c / s for c in row] for row in matrix]


def fallback_predict(home_code: str, away_code: str, home_name: str, away_name: str) -> MarketMatch:
    """Build a MarketMatch for a match with no odds, using ELO fallback."""
    elo_h = _elo_for(home_code)
    elo_a = _elo_for(away_code)
    lam_h, lam_a = _poisson_lambdas_from_elo(elo_h, elo_a)
    matrix = _build_score_matrix(lam_h, lam_a)
    flat = sorted(
        [(f"{i}-{j}", matrix[i][j]) for i in range(11) for j in range(11)],
        key=lambda kv: -kv[1],
    )
    top5 = flat[:5]
    # 1X2 from matrix
    p_h = sum(matrix[i][j] for i in range(11) for j in range(11) if i > j)
    p_d = sum(matrix[i][j] for i in range(11) for j in range(11) if i == j)
    p_a = sum(matrix[i][j] for i in range(11) for j in range(11) if i < j)
    if p_h > p_a and p_h > p_d:
        pick = "home"
    elif p_a > p_h and p_a > p_d:
        pick = "away"
    else:
        pick = "draw"
    best = None
    for i in range(11):
        for j in range(11):
            outcome = "home" if i > j else ("away" if j > i else "draw")
            if outcome != pick:
                continue
            if best is None or matrix[i][j] > best[1]:
                best = (f"{i}-{j}", matrix[i][j])
    p_pick = max(p_h, p_d, p_a)
    if p_pick > 0.55:
        conf = "high"
    elif p_pick > 0.40:
        conf = "medium"
    else:
        conf = "low"
    return MarketMatch(
        event_id="(no odds)",
        p_home=p_h, p_draw=p_d, p_away=p_a,
        expected_total=lam_h + lam_a,
        over_under_line=None,
        home_name=home_name, away_name=away_name,
        top_scores=top5, pick=pick, pick_score=best[0], pick_prob=best[1],
        confidence=conf,
    )


def _build_odds_dump() -> dict:
    """Cache current ESPN odds for the report."""
    odds_map = fetch_odds("2026-06-14")
    out = {}
    for eid, o in odds_map.items():
        probs = market_probs(o)
        out[eid] = {
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
    return out


def main() -> None:
    fx = fetch_fixtures("2026-06-14")
    # Build lookup keyed by numeric ESPN event id (760xxx) and fixture_id (Dongqiudi 5xxxxx)
    lookup = {f.fixture_id: (f.home_team, f.away_team, f.home_code, f.away_code) for f in fx}

    print("\n" + "=" * 60)
    print("今晚 5 场比赛预测（赔率驱动 · DraftKings / ESPN）")
    print("=" * 60 + "\n")

    # Manually map the 5 tonight's matches to their ESPN event IDs
    tonight = [
        # (fx_id, espn_id, home_code, away_code, home_name, away_name)
        ("AUS-TUR", "760421", "AUS", "TUR", "澳大利亚", "土耳其"),
        ("GER-CUW", "760422", "GER", "CUW", "德国", "库拉索"),
        ("NED-JPN", "760425", "NED", "JPN", "荷兰", "日本"),
        ("CIV-ECU", "760423", "CIV", "ECU", "科特迪瓦", "厄瓜多尔"),
        ("SWE-TUN", "760424", "SWE", "TUN", "瑞典", "突尼斯"),
    ]

    odds_map = fetch_odds("2026-06-14")
    for tag, eid, h_code, a_code, home, away in tonight:
        odds = odds_map.get(eid)
        if odds is not None:
            m = predict_match(eid, home, away, odds)
            if m is not None:
                m.event_id = f"{eid} (DraftKings)"
        else:
            m = fallback_predict(h_code, a_code, home, away)
            m.event_id = f"{eid} (无赔率 · ELO fallback)"

        if m is None:
            continue

        pick_label = {
            "home": home,
            "away": away,
            "draw": "平局",
        }[m.pick]
        conf_zh = {"high": "高", "medium": "中", "low": "低"}.get(m.confidence, "—")

        print(f"🏟️  {home} vs {away}  (赔率源: {m.event_id})")
        print(f"    ⏰ {m.event_id}  ·  {m.over_under_line and ('O/U ' + str(m.over_under_line) + ' 球') or '无O/U'}")
        print(f"    胜 {m.p_home:.1%}  |  平 {m.p_draw:.1%}  |  负 {m.p_away:.1%}   ·  期望总进球 {m.expected_total:.2f}")
        print(f"    推荐: {pick_label}  ·  比分: {m.pick_score} ({m.pick_prob*100:.1f}%)  ·  信心: {conf_zh}")
        print(f"    Top 5 比分:  " + "  ".join(f"{s}({p*100:.1f}%)" for s, p in m.top_scores))
        print()

    # Persist odds snapshot
    Path("缓存").mkdir(exist_ok=True)
    snapshot = _build_odds_dump()
    with open("缓存/tonight_odds_snapshot.json", "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    print(f"📊 赔率快照已保存: 缓存/tonight_odds_snapshot.json")


if __name__ == "__main__":
    main()
