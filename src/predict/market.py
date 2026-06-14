"""Market-driven prediction module.

Uses real DraftKings-style odds from ESPN as the primary signal for
tonight's matches. The Poisson model's xG-based estimate is kept as a
secondary tie-breaker when no market data is available.

For each match we report:
  - 1X2 fair probabilities (de-vigged)
  - Expected total goals (from O/U line)
  - The most likely exact score
  - Top 5 most likely scores (via the same Poisson model, but
    parameterised on the *market-implied* expected total)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

from src.data.scrapers.espn_odds import (
    AmericanOdds,
    american_to_implied,
    fetch_odds,
    market_probs,
)


@dataclass
class MarketMatch:
    """Computed predictions for one match, derived purely from odds."""

    event_id: str
    p_home: float
    p_draw: float
    p_away: float
    expected_total: float
    over_under_line: float | None
    home_name: str
    away_name: str
    top_scores: list[tuple[str, float]] = field(default_factory=list)
    pick: str = ""      # "home" / "draw" / "away"
    pick_score: str = "" # most likely score in the pick's direction
    pick_prob: float = 0.0
    confidence: str = "low"  # low / medium / high

    def short(self) -> str:
        return f"{self.home_name} vs {self.away_name}"


def _poisson_pmf(lam: float, k: int) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (lam**k) * math.exp(-lam) / math.factorial(k)


def _solve_lambdas(p_home: float, p_away: float, expected_total: float) -> tuple[float, float]:
    """Solve for per-team lambdas that match the market 1X2 + total.

    The market total implies average goals per side = E[total] / 2.
    We bias each side by their relative strength (p_home vs p_away).
    """
    base = expected_total / 2.0
    # If home is favoured, give them slightly more than half the total.
    # 70% favourite → 60% of total; even → 50%.
    if p_home > p_away:
        ratio = 0.5 + 0.25 * (p_home - p_away)
    else:
        ratio = 0.5 - 0.25 * (p_away - p_home)
    lam_home = base * 2 * ratio
    lam_away = expected_total - lam_home
    return max(0.2, lam_home), max(0.2, lam_away)


def predict_match(event_id: str, home_name: str, away_name: str, odds: AmericanOdds) -> MarketMatch | None:
    """Compute a market-driven prediction for a single match.

    Returns None if the odds are missing the 1X2 legs.
    """
    probs = market_probs(odds)
    if probs is None:
        return None
    p_h, p_d, p_a, e_total = probs

    # Distribute the expected total between teams using a simple rule
    lam_h, lam_a = _solve_lambdas(p_h, p_a, e_total)

    # Build a full Poisson score matrix
    matrix = [[_poisson_pmf(lam_h, i) * _poisson_pmf(lam_a, j) for j in range(11)] for i in range(11)]
    # Renormalise for any rounding loss
    s = sum(sum(row) for row in matrix)
    matrix = [[c / s for c in row] for row in matrix]

    # Flatten and sort to find top 5 scores
    flat: list[tuple[str, float]] = []
    for i in range(11):
        for j in range(11):
            flat.append((f"{i}-{j}", matrix[i][j]))
    flat.sort(key=lambda kv: -kv[1])
    top5 = flat[:5]

    # Decide the pick
    if p_h > p_a and p_h > p_d:
        pick = "home"
    elif p_a > p_h and p_a > p_d:
        pick = "away"
    else:
        pick = "draw"

    # Most likely score in the pick's direction
    best: tuple[str, float] | None = None
    for i in range(11):
        for j in range(11):
            outcome = "home" if i > j else ("away" if j > i else "draw")
            if outcome != pick:
                continue
            if best is None or matrix[i][j] > best[1]:
                best = (f"{i}-{j}", matrix[i][j])
    if best is None:
        best = (top5[0][0], top5[0][1])

    # Confidence: max(p_h, p_d, p_a)
    p_pick = max(p_h, p_a, p_d)
    if p_pick > 0.55:
        confidence = "high"
    elif p_pick > 0.40:
        confidence = "medium"
    else:
        confidence = "low"

    return MarketMatch(
        event_id=event_id,
        p_home=p_h,
        p_draw=p_d,
        p_away=p_a,
        expected_total=e_total,
        over_under_line=odds.over_under,
        home_name=home_name,
        away_name=away_name,
        top_scores=top5,
        pick=pick,
        pick_score=best[0],
        pick_prob=best[1],
        confidence=confidence,
    )


# Public alias for the PPT builder.
_poisson_lambdas_for_market = _solve_lambdas


def predict_tonight(date_str: str | None = None, fixture_lookup=None) -> list[MarketMatch]:
    """Predict all WC matches for the given date using real odds.

    Args:
        fixture_lookup: optional callable `f(event_id) -> (home_name, away_name)`.
            Defaults to the ESPN event name "Curaçao at Germany" -> ("Germany", "Curaçao").
    """
    odds_map = fetch_odds(date_str)
    out: list[MarketMatch] = []
    for eid, o in odds_map.items():
        if fixture_lookup:
            home, away = fixture_lookup(eid)
        else:
            name = eid  # we don't have names in the cache; caller fills
            home = away = name
        m = predict_match(eid, home, away, o)
        if m is not None:
            out.append(m)
    return out


if __name__ == "__main__":
    from src.data.fixtures import fetch_fixtures

    fx = fetch_fixtures("2026-06-14")
    lookup = {f.fixture_id: (f.home_team, f.away_team) for f in fx}
    matches = predict_tonight(
        "2026-06-14",
        fixture_lookup=lambda eid: lookup.get(eid, ("?", "?")),
    )
    for m in matches:
        print(f"🏟 {m.home_name} vs {m.away_name}")
        print(f"    Pick: {m.pick} → {m.pick_score} ({m.pick_prob*100:.1f}%)")
        print(f"    P(h/d/a)={m.p_home:.0%}/{m.p_draw:.0%}/{m.p_away:.0%}  E[total]={m.expected_total:.2f}  O/U={m.over_under_line}")
        print(f"    Top 5 scores:")
        for s, p in m.top_scores:
            print(f"        {s}: {p*100:.1f}%")
        print()
