"""XGBoost-style gradient boosting classifier for match outcome.

Trained on synthetic but realistic match data calibrated to ELO/team-strength
distributions, since we have no access to a large labelled international match
dataset at runtime.  The synthetic generator mimics the structure of real
features so the model can rank-order teams in a sensible way.

For production use, replace `_generate_training_data` with a real loader
that consumes `data/historical_matches.csv`.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler

from src.utils.models import MatchInput, Team, TeamStats


@dataclass
class TrainedModel:
    classifier: GradientBoostingClassifier
    scaler: StandardScaler
    feature_names: list[str]


_FEATURE_NAMES = [
    "elo_diff",
    "elo_a",
    "elo_b",
    "rank_diff",
    "xg_diff",
    "form_diff",
    "h2h_a_wins",
    "h2h_b_wins",
    "neutral",
    "knockout",
]


def _build_features(
    team_a: Team,
    team_b: Team,
    stats_a: TeamStats,
    stats_b: TeamStats,
    match: MatchInput,
    h2h_a_wins: int = 0,
    h2h_b_wins: int = 0,
) -> np.ndarray:
    form_a = stats_a.last_10_wins - stats_a.last_10_losses
    form_b = stats_b.last_10_wins - stats_b.last_10_losses
    feats = [
        team_a.elo - team_b.elo,
        team_a.elo,
        team_b.elo,
        team_b.fifa_ranking - team_a.fifa_ranking,  # positive => A is better
        stats_a.xg_per_game - stats_b.xg_per_game,
        form_a - form_b,
        h2h_a_wins,
        h2h_b_wins,
        1.0 if match.is_neutral else 0.0,
        1.0 if match.stage in {"round_of_16", "quarterfinal", "semifinal", "final"} else 0.0,
    ]
    return np.array(feats, dtype=float).reshape(1, -1)


def _generate_training_data(n: int = 5000, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """Synthetic but realistic labelled training set.

    Outcomes (0=A win, 1=draw, 2=B win) are sampled from a softmax of an
    underlying skill differential so the model can learn the mapping.
    """
    rng = np.random.default_rng(seed)
    X_rows = []
    y = []
    for _ in range(n):
        elo_a = rng.normal(1850, 130)
        elo_b = elo_a + rng.normal(0, 220)
        rank_a = rng.integers(1, 80)
        rank_b = rng.integers(1, 80)
        xg_a = rng.normal(1.5, 0.4)
        xg_b = rng.normal(1.5, 0.4)
        form_a = rng.normal(0, 3)
        form_b = form_a + rng.normal(0, 4)
        h2h_a = rng.integers(0, 6)
        h2h_b = rng.integers(0, 6)
        neutral = rng.choice([0.0, 1.0])
        knockout = rng.choice([0.0, 1.0])
        feats = [
            elo_a - (elo_a + rng.normal(0, 220)),
            elo_a,
            elo_a + rng.normal(0, 220),
            rank_b - rank_a,
            xg_a - xg_b,
            form_a - form_b,
            h2h_a,
            h2h_b,
            neutral,
            knockout,
        ]
        # Underlying skill differential
        skill = (
            0.012 * (elo_a - elo_b)
            + 0.4 * (xg_a - xg_b)
            + 0.05 * (form_a - form_b)
            + 0.2 * (rank_b - rank_a) / 50
        )
        # Map to probability via softmax with draw bump
        p_win = 1 / (1 + np.exp(-skill * 4))
        p_draw = 0.28 - 0.10 * abs(skill)
        p_draw = max(0.10, p_draw)
        p_loss = 1 - p_win
        # Renormalise over win/draw/loss
        total = p_win + p_draw + p_loss
        probs = [p_win / total, p_draw / total, p_loss / total]
        outcome = rng.choice([0, 1, 2], p=probs)
        X_rows.append(feats)
        y.append(outcome)
    return np.array(X_rows), np.array(y)


_MODEL_CACHE: TrainedModel | None = None


def get_trained_model() -> TrainedModel:
    global _MODEL_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE
    X, y = _generate_training_data()
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    clf = GradientBoostingClassifier(
        n_estimators=120, max_depth=3, learning_rate=0.08, random_state=42
    )
    clf.fit(X_scaled, y)
    _MODEL_CACHE = TrainedModel(classifier=clf, scaler=scaler, feature_names=_FEATURE_NAMES)
    return _MODEL_CACHE


def predict_ml(
    team_a: Team,
    team_b: Team,
    stats_a: TeamStats,
    stats_b: TeamStats,
    match: MatchInput,
    h2h_a_wins: int = 0,
    h2h_b_wins: int = 0,
) -> tuple[float, float, float]:
    """Predict (P(win), P(draw), P(loss)) for team A using the ML model."""
    model = get_trained_model()
    feats = _build_features(team_a, team_b, stats_a, stats_b, match, h2h_a_wins, h2h_b_wins)
    feats_scaled = model.scaler.transform(feats)
    probs = model.classifier.predict_proba(feats_scaled)[0]
    # Classes are sorted: 0=win, 1=draw, 2=loss
    return float(probs[0]), float(probs[1]), float(probs[2])
