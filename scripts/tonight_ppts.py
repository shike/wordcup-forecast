#!/usr/bin/env python3
"""Build PPTs for tonight's 5 matches, driven by real DraftKings odds.

Outputs:
  - 5 PPT files in 输出/tonight_<match>.pptx
  - 1 markdown report 输出/tonight_predictions.md

The prediction engine uses real odds (1X2 + O/U) when available,
falling back to the ELO-driven Poisson model only for the in-progress
match that the market hasn't priced.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from loguru import logger

from src.data.scrapers.espn_odds import (
    AmericanOdds,
    fetch_odds,
    market_probs,
)
from src.predict.market import (
    MarketMatch,
    _poisson_pmf,
    predict_match,
)
from src.predict.market import _solve_lambdas


def _fallback_lambdas(elo_h: int, elo_a: int) -> tuple[float, float]:
    base = 1.27
    diff = (elo_h - elo_a) / 100.0
    return max(0.5, base + 0.4 * diff), max(0.5, base - 0.4 * diff)


def _elo_for(code: str) -> int:
    table = {
        "GER": 1960, "CUW": 1620, "NED": 2030, "JPN": 1910, "CIV": 1790,
        "ECU": 1840, "SWE": 1820, "TUN": 1730, "AUS": 1810, "TUR": 1840,
        "ARG": 2130, "BRA": 2030, "ESP": 1980, "FRA": 2090, "ENG": 2010,
        "ITA": 1900, "POR": 1990, "MEX": 1880, "USA": 1860, "URU": 1900,
    }
    return table.get(code, 1800)


def build_match_for_ppt(
    eid: str,
    home_name: str,
    away_name: str,
    h_code: str,
    a_code: str,
    odds_map: dict,
) -> MarketMatch:
    """Build a MarketMatch. Falls back to ELO if no odds."""
    odds = odds_map.get(eid)
    if odds is not None and odds.home is not None:
        m = predict_match(eid, home_name, away_name, odds)
        if m is not None:
            m.event_id = f"{eid} (DraftKings)"
            return m
    elo_h, elo_a = _elo_for(h_code), _elo_for(a_code)
    lam_h, lam_a = _fallback_lambdas(elo_h, elo_a)
    matrix = [[_poisson_pmf(lam_h, i) * _poisson_pmf(lam_a, j) for j in range(11)] for i in range(11)]
    s = sum(sum(row) for row in matrix)
    matrix = [[c / s for c in row] for row in matrix]
    p_h = sum(matrix[i][j] for i in range(11) for j in range(11) if i > j)
    p_d = sum(matrix[i][j] for i in range(11) for j in range(11) if i == j)
    p_a = sum(matrix[i][j] for i in range(11) for j in range(11) if i < j)
    flat = sorted([(f"{i}-{j}", matrix[i][j]) for i in range(11) for j in range(11)], key=lambda kv: -kv[1])
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
    conf = "high" if p_pick > 0.55 else ("medium" if p_pick > 0.40 else "low")
    return MarketMatch(
        event_id=f"{eid} (ELO fallback · 无赔率)",
        p_home=p_h, p_draw=p_d, p_away=p_a,
        expected_total=lam_h + lam_a, over_under_line=None,
        home_name=home_name, away_name=away_name,
        top_scores=flat[:5], pick=pick, pick_score=best[0], pick_prob=best[1],
        confidence=conf,
    )


def render_markdown(matches: list[tuple[str, MarketMatch]]) -> str:
    lines: list[str] = []
    lines.append("# 今晚 5 场比赛预测（赔率驱动 · DraftKings / ESPN）\n")
    lines.append("> 数据源：ESPN + DraftKings 实时赔率。无赔率的比赛（如进行中的 AUS-TUR）使用 ELO 兜底。\n")
    for tag, m in matches:
        home, away = m.home_name, m.away_name
        pick_label = {
            "home": home, "away": away, "draw": "平局",
        }[m.pick]
        ou = f"O/U {m.over_under_line}" if m.over_under_line else "无O/U"
        lines.append(f"## {home} vs {away}")
        lines.append(f"- **数据源**: {m.event_id}")
        lines.append(f"- **O/U**: {ou}  ·  **期望总进球**: {m.expected_total:.2f}")
        lines.append(f"- **1X2 概率**: 胜 {m.p_home:.1%} · 平 {m.p_draw:.1%} · 负 {m.p_away:.1%}")
        lines.append(f"- **推荐**: {pick_label}  ·  **比分**: {m.pick_score} ({m.pick_prob*100:.1f}%)  ·  **信心**: {m.confidence}")
        lines.append("- **Top 5 比分**:")
        for s, p in m.top_scores:
            lines.append(f"  - {s}: {p*100:.1f}%")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    tonight = [
        ("AUS-TUR", "760421", "AUS", "TUR", "澳大利亚", "土耳其"),
        ("GER-CUW", "760422", "GER", "CUW", "德国", "库拉索"),
        ("NED-JPN", "760425", "NED", "JPN", "荷兰", "日本"),
        ("CIV-ECU", "760423", "CIV", "ECU", "科特迪瓦", "厄瓜多尔"),
        ("SWE-TUN", "760424", "SWE", "TUN", "瑞典", "突尼斯"),
    ]

    odds_map = fetch_odds("2026-06-14")
    print(f"📊 赔率条数: {len(odds_map)}")

    Path("输出").mkdir(exist_ok=True)
    matches: list[tuple[str, MarketMatch]] = []

    for tag, eid, h_code, a_code, home, away in tonight:
        m = build_match_for_ppt(eid, home, away, h_code, a_code, odds_map)
        matches.append((tag, m))
        pick_label = {"home": home, "away": away, "draw": "平局"}[m.pick]
        ou = f"O/U {m.over_under_line}" if m.over_under_line else "无O/U"
        conf_zh = {"high": "高", "medium": "中", "low": "低"}[m.confidence]
        print(f"🏟  {home} vs {away}  ·  {m.event_id}")
        print(f"   胜 {m.p_home:.0%} · 平 {m.p_draw:.0%} · 负 {m.p_away:.0%}   ·  {ou}   ·  E[total]={m.expected_total:.2f}")
        print(f"   推荐: {pick_label} → {m.pick_score} ({m.pick_prob*100:.1f}%)  ·  信心 {conf_zh}")
        print()

    # Build PPT for the 4 matches with real odds
    from src.pipeline import run_prediction
    from src.data.team_data import get_team

    for tag, m in matches:
        # Look up team codes in projects team_data
        try:
            h_team = get_team(_to_team_code(m.home_name))
            a_team = get_team(_to_team_code(m.away_name))
        except Exception:
            continue
        # Use the regular prediction pipeline to build the PPT (slides 1-21)
        # but the cover / final pages will show the **market** prediction,
        # not the xG model.
        try:
            from src.predict.market import _poisson_lambdas_for_market
            from src.models.poisson import predict_market_aware
            from src.models.adjustments import adjustment_factor, apply_adjustments
            from src.utils.models import QualitativeFactors, MatchInput
            from datetime import datetime

            # Build TeamStats lite from market
            from src.data.features import FeatureBuilder
            builder = FeatureBuilder()
            stats_a = builder.build_team_stats(h_team.code, "2026-06-14", last_n=50, min_matches=1)
            stats_b = builder.build_team_stats(a_team.code, "2026-06-14", last_n=50, min_matches=1)
            if stats_a is None or stats_b is None:
                continue

            qual_a = QualitativeFactors()
            qual_b = QualitativeFactors()
            match = MatchInput(
                team_a=h_team, team_b=a_team,
                match_date="2026-06-15", stage="group", venue="TBD", is_neutral=True,
            )

            # Use the new market-aware Poisson model. Market 1X2 + O/U
            # are the dominant signals, xG provides a soft prior.
            probs, (lam_h, lam_a), matrix, _ = predict_market_aware(
                stats_a, stats_b,
                elo_a=h_team.elo, elo_b=a_team.elo,
                sample_size_a=50, sample_size_b=50,
                p_home_market=m.p_home,
                p_draw_market=m.p_draw,
                p_away_market=m.p_away,
                expected_total_market=m.expected_total,
                market_weight=0.7,  # market dominates for tonight
            )
            # Re-anchor 1X2 to market values directly (don't lose precision)
            probs = (m.p_home, m.p_draw, m.p_away)

            # Run Monte Carlo with the market-derived lambdas
            from src.models.monte_carlo import run_monte_carlo
            mc = run_monte_carlo(lam_h, lam_a, match, n=10000, elo_a=h_team.elo, elo_b=a_team.elo)
            # Force the 1X2 probs to the market's de-vigged values
            mc = mc.__class__(
                simulations=mc.simulations,
                win_a=probs[0], draw=probs[1], win_b=probs[2],
                top_scores=mc.top_scores, distribution=mc.distribution,
                extra_time_prob=mc.extra_time_prob, penalties_prob=mc.penalties_prob,
            )
            from src.models.poisson import _RHO_DEFAULT

            from src.utils.models import (
                InjuryReport, Lineup, Matchup, ModelProbabilities,
                MonteCarloResult, Player, PredictionResult, QualitativeFactors,
                Team, TeamStats,
            )
            from src.lineup.formations import load_formations
            from src.lineup.matchup_engine import generate_matchups
            from src.lineup.predictor import predict_lineup
            lineup_a, formation_a, injuries_a = predict_lineup(h_team, match, "A")
            lineup_b, formation_b, injuries_b = predict_lineup(a_team, match, "B")
            matchups = generate_matchups(lineup_a, lineup_b, h_team.code, a_team.code)
            mp = ModelProbabilities(
                primary_model="market-odds",
                win_draw_loss=probs, expected_goals=(lam_h, lam_a),
                confidence=m.confidence, data_quality=1.0,
                sample_size_a=50, sample_size_b=50, elo_prior_weight=0.0,
            )
            result = PredictionResult(
                match=match, team_a_stats=stats_a, team_b_stats=stats_b,
                qualitative_a=qual_a, qualitative_b=qual_b,
                injuries_a=injuries_a, injuries_b=injuries_b,
                lineup_a=lineup_a, lineup_b=lineup_b,
                model_probs=mp, monte_carlo=mc,
                key_matchups=matchups,
                recommended_pick={"home": "A", "away": "B", "draw": "draw"}[m.pick],
                confidence=m.confidence,
                key_risks=[f"数据源: 实时 DraftKings 赔率 (O/U {m.over_under_line or '—'} 球, 期望 {m.expected_total:.2f} 球) · 模型: market-aware Poisson (market_weight=0.7)"],
                pre_match_news=[],
            )
            from src.ppt.builder import build_ppt
            output_path = Path(f"输出/tonight_{tag.replace('-', '_')}.pptx")
            build_ppt(result, lang="zh", output_path=output_path)
            print(f"   ✅ {output_path}")
        except Exception as exc:
            logger.warning(f"   PPT build failed for {tag}: {exc}")

    # Write the markdown report
    md = render_markdown(matches)
    Path("输出/tonight_predictions.md").write_text(md, encoding="utf-8")
    print(f"\n📝 报告: 输出/tonight_predictions.md")


def _to_team_code(name: str) -> str:
    """Map Chinese team name back to project 3-letter code."""
    mapping = {
        "澳大利亚": "AUS", "土耳其": "TUR", "德国": "GER", "库拉索": "CUW",
        "荷兰": "NED", "日本": "JPN", "科特迪瓦": "CIV", "厄瓜多尔": "ECU",
        "瑞典": "SWE", "突尼斯": "TUN",
    }
    return mapping.get(name, name[:3].upper())


if __name__ == "__main__":
    main()
