"""Backtesting metrics for probabilistic football predictions."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MetricsResult:
    rps: float
    log_loss: float
    brier: float
    accuracy: float
    calibration_error: float
    n: int


def _rps_single(predicted: tuple[float, float, float], observed: tuple[float, float, float]) -> float:
    """Ranked Probability Score for one match.

    predicted and observed are (P(win), P(draw), P(loss)) for team A.
    """
    pred_cum = np.cumsum(predicted)
    obs_cum = np.cumsum(observed)
    return float(np.sum((pred_cum - obs_cum) ** 2) / (len(predicted) - 1))


def compute_metrics(
    predictions: list[tuple[float, float, float]],
    outcomes: list[tuple[float, float, float]],
) -> MetricsResult:
    """Compute aggregate metrics over a list of match predictions."""
    n = len(predictions)
    if n == 0:
        return MetricsResult(0.0, 0.0, 0.0, 0.0, 0.0, 0)

    rps_values = [_rps_single(p, o) for p, o in zip(predictions, outcomes)]
    rps = sum(rps_values) / n

    log_loss_values = []
    brier_values = []
    correct = 0
    for p, o in zip(predictions, outcomes):
        # outcome index: 0=win, 1=draw, 2=loss
        outcome_idx = o.index(1.0)
        pred_prob = p[outcome_idx]
        log_loss_values.append(-math.log(max(1e-10, pred_prob)))
        brier_values.append((pred_prob - 1.0) ** 2)
        if p.index(max(p)) == outcome_idx:
            correct += 1

    log_loss = sum(log_loss_values) / n
    brier = sum(brier_values) / n
    accuracy = correct / n

    # Expected Calibration Error (ECE) using 10 bins
    calibration_error = _expected_calibration_error(predictions, outcomes)

    return MetricsResult(
        rps=rps,
        log_loss=log_loss,
        brier=brier,
        accuracy=accuracy,
        calibration_error=calibration_error,
        n=n,
    )


def _expected_calibration_error(
    predictions: list[tuple[float, float, float]],
    outcomes: list[tuple[float, float, float]],
    n_bins: int = 10,
) -> float:
    """Compute Expected Calibration Error for the win probability."""
    win_probs = [p[0] for p in predictions]
    win_observed = [o[0] for o in outcomes]

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    total_error = 0.0
    total_count = 0
    for i in range(n_bins):
        low, high = bin_edges[i], bin_edges[i + 1]
        if i == n_bins - 1:
            mask = [(low <= p <= high) for p in win_probs]
        else:
            mask = [(low <= p < high) for p in win_probs]
        count = sum(mask)
        if count == 0:
            continue
        avg_pred = sum(win_probs[j] for j, m in enumerate(mask) if m) / count
        avg_obs = sum(win_observed[j] for j, m in enumerate(mask) if m) / count
        total_error += count * abs(avg_pred - avg_obs)
        total_count += count

    return total_error / total_count if total_count > 0 else 0.0


def outcome_vector(goals_a: int, goals_b: int) -> tuple[float, float, float]:
    """Convert a score into a (win, draw, loss) vector for team A."""
    if goals_a > goals_b:
        return 1.0, 0.0, 0.0
    if goals_a == goals_b:
        return 0.0, 1.0, 0.0
    return 0.0, 0.0, 1.0
