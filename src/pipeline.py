"""Main prediction pipeline that wires all modules together."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from loguru import logger

from src.lineup.formations import load_formations
from src.lineup.matchup_engine import generate_matchups
from src.lineup.predictor import predict_lineup
from src.models.adjustments import adjustment_factor, apply_adjustments
from src.models.elo import predict_elo
from src.models.monte_carlo import run_monte_carlo
from src.models.poisson import expected_goals, predict_poisson
from src.utils.models import (
    InjuryReport,
    Lineup,
    MatchInput,
    Matchup,
    ModelProbabilities,
    MonteCarloResult,
    Player,
    PredictionResult,
    QualitativeFactors,
    Team,
    TeamStats,
)
from src.utils.config import config


# ---------- mock data sources (real impl lives in M3) ----------

def _default_stats(team: Team) -> TeamStats:
    """Derive rough baseline stats from FIFA ranking (lower rank = stronger)."""
    rank_factor = max(0.5, 1.5 - (team.fifa_ranking - 1) * 0.015)
    return TeamStats(
        team_code=team.code,
        goals_per_game=round(1.0 + rank_factor * 0.7, 2),
        conceded_per_game=round(1.6 - rank_factor * 0.5, 2),
        xg_per_game=round(1.0 + rank_factor * 0.8, 2),
        xga_per_game=round(1.5 - rank_factor * 0.4, 2),
        clean_sheet_rate=round(0.20 + rank_factor * 0.15, 2),
        last_10_wins=int(4 + rank_factor * 3),
        last_10_draws=3,
        last_10_losses=int(6 - rank_factor * 3),
        starter_strength=60 + rank_factor * 25,
        bench_strength=50 + rank_factor * 18,
    )


def _default_qualitative(team: Team) -> QualitativeFactors:
    return QualitativeFactors(
        tactical=6.5 + min(2.5, (2000 - team.elo) / -200),
        experience=6.0 + min(3.0, (team.fifa_ranking <= 10) * 1.5),
        psychology=7.0,
        venue_factor=7.0,
        schedule=7.0,
    )


# ---------- main entry point ----------

def run_prediction(
    team_a: Team,
    team_b: Team,
    match_date: str,
    stage: str,
    venue: str,
    lang: str = "bilingual",
    simulations: int = 10_000,
) -> PredictionResult:
    """Run full prediction and return a PredictionResult."""
    logger.info("Loading data sources…")
    stats_a = _default_stats(team_a)
    stats_b = _default_stats(team_b)
    qual_a = _default_qualitative(team_a)
    qual_b = _default_qualitative(team_b)

    match = MatchInput(
        team_a=team_a,
        team_b=team_b,
        match_date=match_date,
        stage=stage,
        venue=venue,
        is_neutral=True,
    )

    logger.info("Predicting lineups…")
    lineup_a, formation_a, injuries_a = predict_lineup(team_a, match, "A")
    lineup_b, formation_b, injuries_b = predict_lineup(team_b, match, "B")
    logger.info(f"  {team_a.code}: {formation_a}")
    logger.info(f"  {team_b.code}: {formation_b}")

    logger.info("Running ELO + Poisson + ML…")
    elo_p = predict_elo(team_a, team_b, neutral=True)
    poi_p, (lam_a, lam_b), matrix = predict_poisson(team_a, team_b, stats_a, stats_b)
    ml_p = _ml_probs(team_a, team_b, stats_a, stats_b, match)

    # Apply qualitative adjustments
    factor_a = adjustment_factor(stats_a, qual_a, is_home=False, knockout=match.stage != "group")
    factor_b = adjustment_factor(stats_b, qual_b, is_home=False, knockout=match.stage != "group")
    final_a = apply_adjustments(elo_p[0], elo_p[1], elo_p[2], factor_a, factor_b)

    # Weighted consensus
    consensus = (
        0.30 * final_a[0] + 0.40 * poi_p[0] + 0.30 * ml_p[0],
        0.30 * final_a[1] + 0.40 * poi_p[1] + 0.30 * ml_p[1],
        0.30 * final_a[2] + 0.40 * poi_p[2] + 0.30 * ml_p[2],
    )
    consensus = _renormalise(*consensus)

    max_prob = max(consensus)
    if max_prob > 0.55:
        confidence = "high"
    elif max_prob > 0.40:
        confidence = "medium"
    else:
        confidence = "low"

    model_probs = ModelProbabilities(
        elo=elo_p,
        poisson=poi_p,
        ml=ml_p,
        consensus=consensus,
        expected_goals=(lam_a, lam_b),
        confidence=confidence,
    )

    logger.info("Monte Carlo simulation…")
    mc = run_monte_carlo(lam_a, lam_b, match, n=simulations)

    logger.info("Generating key matchups…")
    matchups = generate_matchups(lineup_a, lineup_b, team_a.code, team_b.code)

    if consensus[0] > consensus[1] and consensus[0] > consensus[2]:
        pick = "A"
    elif consensus[2] > consensus[1] and consensus[2] > consensus[0]:
        pick = "B"
    else:
        pick = "draw"

    key_risks = _generate_key_risks(team_a, team_b, injuries_a, injuries_b, match)

    return PredictionResult(
        match=match,
        team_a_stats=stats_a,
        team_b_stats=stats_b,
        qualitative_a=qual_a,
        qualitative_b=qual_b,
        injuries_a=injuries_a,
        injuries_b=injuries_b,
        lineup_a=lineup_a,
        lineup_b=lineup_b,
        model_probs=model_probs,
        monte_carlo=mc,
        key_matchups=matchups,
        recommended_pick=pick,
        confidence=confidence,
        key_risks=key_risks,
    )


def _renormalise(p_w: float, p_d: float, p_l: float) -> tuple[float, float, float]:
    total = p_w + p_d + p_l
    return p_w / total, p_d / total, p_l / total


def _ml_probs(team_a, team_b, stats_a, stats_b, match):
    from src.models.ml_model import predict_ml

    return predict_ml(team_a, team_b, stats_a, stats_b, match)


def _generate_key_risks(
    team_a: Team,
    team_b: Team,
    injuries_a: list[InjuryReport],
    injuries_b: list[InjuryReport],
    match: MatchInput,
) -> list[str]:
    risks: list[str] = []
    for inj in injuries_a:
        if inj.impact == "critical":
            risks.append(
                f"{team_a.name_zh} 核心球员 {inj.player.name} 因伤缺阵，攻防体系可能受重大影响"
            )
    for inj in injuries_b:
        if inj.impact == "critical":
            risks.append(
                f"{team_b.name_zh} 核心球员 {inj.player.name} 因伤缺阵，攻防体系可能受重大影响"
            )
    elo_gap = abs(team_a.elo - team_b.elo)
    if elo_gap > 150:
        risks.append("两队实力差距较大，弱队反击效率可能成为变数")
    if match.stage in {"knockout"} or "final" in match.stage or "semifinal" in match.stage:
        risks.append("淘汰赛 90 分钟内平局将进入加时和点球，心理素质与体能是关键")
    if not risks:
        risks.append("双方阵容齐整，X 因素：定位球、门将失误、裁判判罚")
    return risks
