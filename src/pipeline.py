"""Main prediction pipeline that wires all modules together.

The pipeline uses real match data from the SQLite warehouse. If a team lacks
real matches the prediction is refused with a clear error — no synthetic or
neutral statistics are ever produced.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from loguru import logger

from src.data.features import FeatureBuilder
from src.data.repository import EloRepository, MatchRepository
from src.data.scrapers import zhibo8 as zhibo8_scraper
from src.lineup.formations import load_formations
from src.lineup.matchup_engine import generate_matchups
from src.lineup.predictor import predict_lineup
from src.models.adjustments import adjustment_factor, apply_adjustments
from src.models.monte_carlo import run_monte_carlo
from src.models.poisson import predict_poisson
from src.utils.config import config
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


def _default_qualitative(team: Team) -> QualitativeFactors:
    """Minimal qualitative baseline from seed data."""
    return QualitativeFactors(
        tactical=6.5 + min(2.5, (2000 - team.elo) / -200),
        experience=6.0 + min(3.0, (team.fifa_ranking <= 10) * 1.5),
        psychology=7.0,
        venue_factor=7.0,
        schedule=7.0,
    )


def _data_quality(stats: TeamStats | None) -> float:
    """Rough data-quality score based on how many fields are real vs zeroed."""
    if stats is None:
        return 0.0
    real_fields = 0
    total_fields = 8
    if stats.goals_per_game > 0:
        real_fields += 1
    if stats.conceded_per_game > 0:
        real_fields += 1
    if stats.xg_per_game > 0:
        real_fields += 1
    if stats.xga_per_game > 0:
        real_fields += 1
    if stats.last_10_wins + stats.last_10_draws + stats.last_10_losses > 0:
        real_fields += 1
    if stats.possession_avg is not None:
        real_fields += 1
    if stats.pressing_intensity > 0:
        real_fields += 1
    if stats.set_piece_goals_pct > 0:
        real_fields += 1
    return real_fields / total_fields


def _confidence(
    max_prob: float,
    data_quality_a: float,
    data_quality_b: float,
    sample_size_a: int,
    sample_size_b: int,
) -> Literal["high", "medium", "low"]:
    """Data-driven confidence label."""
    avg_quality = (data_quality_a + data_quality_b) / 2
    min_sample = min(sample_size_a, sample_size_b)
    if max_prob > 0.55 and avg_quality >= 0.8 and min_sample >= 5:
        return "high"
    if max_prob > 0.40 and avg_quality >= 0.5 and min_sample >= 3:
        return "medium"
    return "low"


def run_prediction(
    team_a: Team,
    team_b: Team,
    match_date: str,
    stage: str,
    venue: str,
    lang: str = "bilingual",
    simulations: int = 10_000,
    db_path: Path | None = None,
) -> PredictionResult:
    """Run full prediction and return a PredictionResult."""
    logger.info("Loading real match data…")
    builder = FeatureBuilder(db_path)
    repo = MatchRepository(db_path)

    # Use a wider window so StatsBomb 2018/2022 data (the only source of
    # player-level stats) can contribute. We still weight recent matches
    # more heavily via the underlying repository ordering.
    stats_a = builder.build_team_stats(team_a.code, match_date, last_n=50, min_matches=1)
    stats_b = builder.build_team_stats(team_b.code, match_date, last_n=50, min_matches=1)

    sample_size_a = repo.count_matches(team_a.code)
    sample_size_b = repo.count_matches(team_b.code)

    # ELO prior: use seed ELO if no historical ELO in warehouse
    elo_repo = EloRepository(db_path)
    elo_a = elo_repo.get_rating(team_a.code, match_date) or team_a.elo
    elo_b = elo_repo.get_rating(team_b.code, match_date) or team_b.elo

    # No synthetic fallback: every team must have real matches in the warehouse.
    if stats_a is None or stats_b is None:
        missing = []
        if stats_a is None:
            missing.append(f"{team_a.name_zh} ({team_a.code})")
        if stats_b is None:
            missing.append(f"{team_b.name_zh} ({team_b.code})")
        raise ValueError(
            f"缺少真实比赛数据，无法预测：{', '.join(missing)}。"
            f"请先运行数据 ingest（python -m src.data.ingest）。"
        )

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

    logger.info("Running Dixon-Coles model…")
    probs, (lam_a, lam_b), matrix, (elo_w_a, elo_w_b) = predict_poisson(
        stats_a, stats_b,
        elo_a=elo_a, elo_b=elo_b,
        sample_size_a=sample_size_a, sample_size_b=sample_size_b,
        home_advantage=1.0,
    )

    # Qualitative adjustments (kept lightweight)
    factor_a = adjustment_factor(stats_a, qual_a, is_home=False, knockout=match.stage != "group")
    factor_b = adjustment_factor(stats_b, qual_b, is_home=False, knockout=match.stage != "group")
    adjusted_probs = apply_adjustments(probs[0], probs[1], probs[2], factor_a, factor_b)

    data_quality_a = _data_quality(stats_a)
    data_quality_b = _data_quality(stats_b)

    confidence = _confidence(
        max(adjusted_probs),
        data_quality_a,
        data_quality_b,
        sample_size_a,
        sample_size_b,
    )

    model_probs = ModelProbabilities(
        primary_model="dixon_coles_xg",
        win_draw_loss=adjusted_probs,
        expected_goals=(lam_a, lam_b),
        confidence=confidence,
        data_quality=(data_quality_a + data_quality_b) / 2,
        sample_size_a=sample_size_a,
        sample_size_b=sample_size_b,
        elo_prior_weight=(elo_w_a + elo_w_b) / 2,
    )

    logger.info("Monte Carlo simulation…")
    mc = run_monte_carlo(lam_a, lam_b, match, n=simulations, elo_a=elo_a, elo_b=elo_b)

    logger.info("Generating key matchups…")
    matchups = generate_matchups(lineup_a, lineup_b, team_a.code, team_b.code)

    if adjusted_probs[0] > adjusted_probs[1] and adjusted_probs[0] > adjusted_probs[2]:
        pick = "A"
    elif adjusted_probs[2] > adjusted_probs[1] and adjusted_probs[2] > adjusted_probs[0]:
        pick = "B"
    else:
        pick = "draw"

    # Use the most likely score that matches the consensus pick so the
    # headline number reflects the actual win/draw/loss verdict rather
    # than a generic 1-1 mode.
    headline_score = mc.predicted_score_for(pick)
    score_prob = mc.distribution.get(headline_score, 0.0)

    key_risks = _generate_key_risks(team_a, team_b, injuries_a, injuries_b, match, confidence)
    pre_match_news = _fetch_pre_match_news(team_a, team_b, match_date)

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
        pre_match_news=pre_match_news,
    )


def _generate_key_risks(
    team_a: Team,
    team_b: Team,
    injuries_a: list[InjuryReport],
    injuries_b: list[InjuryReport],
    match: MatchInput,
    confidence: Literal["high", "medium", "low"],
) -> list[str]:
    risks: list[str] = []
    if confidence == "low":
        risks.append("真实比赛数据不足，预测主要依赖 ELO 先验，可信度有限")
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


def _fetch_pre_match_news(
    team_a: Team,
    team_b: Team,
    match_date: str,
    max_items: int = 6,
) -> list[str]:
    """Fetch recent Zhibo8 headlines and filter for the two teams.

    Used to add Chinese pre-match context to the prediction report. Falls
    back gracefully (returns empty list) if the scraper is unavailable.
    """
    keywords = {
        team_a.name_zh,
        team_a.name_en,
        team_a.code,
        team_b.name_zh,
        team_b.name_en,
        team_b.code,
    }
    try:
        items = zhibo8_scraper.fetch_football_news()
    except Exception as exc:
        logger.debug(f"Zhibo8 news fetch skipped: {exc}")
        return []

    selected: list[str] = []
    for item in items:
        title = item.title or ""
        if not any(kw in title for kw in keywords if kw):
            continue
        # Strip excessive whitespace and trailing whitespace.
        title = " ".join(title.split())
        if title and title not in selected:
            selected.append(title)
            if len(selected) >= max_items:
                break

    if not selected:
        # Fallback: return top football headlines even if no keyword match.
        for item in items[:max_items]:
            title = " ".join((item.title or "").split())
            if title:
                selected.append(title)
    return selected


# Keep load_formations import effective; avoid unused-import warnings by
# referencing it in __all__.
__all__ = ["run_prediction", "load_formations"]
