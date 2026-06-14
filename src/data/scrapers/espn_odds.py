"""ESPN odds scraper.

Fetches real-moneyline + totals odds from ESPN's public scoreboard API.
Used to drive predictions with the actual market consensus rather than
the model's own xG extrapolation.

Odds are returned in American format (e.g. -150, +235). We convert to
implied probabilities using the standard formula:

    p = 1 / (1 + 10 ** (-(decimal - 1)))
    p = 100 / (decimal * 100) if negative else decimal/100

And de-vig the three-way (1X2) market via:
    fair_p = p_raw / sum(p_raw) * 1.0
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests
from loguru import logger

from src.utils.config import config


ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer"
DEFAULT_TIMEOUT = 15


@dataclass
class AmericanOdds:
    """Single outcome odds in American format."""

    home: int | None
    draw: int | None
    away: int | None
    over_under: float | None
    over_odds: int | None
    under_odds: int | None
    provider: str | None


def american_to_implied(odds: int | None) -> float | None:
    """Convert American odds to raw implied probability (no de-vig)."""
    if odds is None:
        return None
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return -odds / (-odds + 100.0)


def american_to_decimal(odds: int | None) -> float | None:
    """Convert American odds to decimal (European) odds."""
    if odds is None:
        return None
    if odds > 0:
        return 1.0 + odds / 100.0
    return 1.0 + 100.0 / -odds


def _devig(p_a: float, p_b: float, p_c: float) -> tuple[float, float, float]:
    """De-vig a 1X2 (or any 3-way) market by simple normalisation.

    The bookmaker's three implied probabilities sum to more than 1.0
    (the overround). We distribute the overround proportionally to
    recover the fair (margin-free) probability for each outcome.
    """
    s = p_a + p_b + p_c
    if s <= 0:
        return 0.34, 0.33, 0.33
    return p_a / s, p_b / s, p_c / s


def _cache_path() -> Path:
    return config.api_cache / "espn_odds_latest.json"


def fetch_odds(date_str: str | None = None) -> dict[str, AmericanOdds]:
    """Fetch DraftKings-style odds for all WC matches on the given date.

    Returns a dict keyed by ESPN event id.
    """
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

    # Use cache if fresh (15 min)
    cache = _cache_path()
    if cache.exists():
        age = datetime.now().timestamp() - cache.stat().st_mtime
        if age < 900:
            try:
                return _parse_odds_cache(json.loads(cache.read_text(encoding="utf-8")))
            except Exception:
                pass

    url = f"{ESPN_SCOREBOARD}/fifa.world/scoreboard"
    try:
        response = requests.get(url, params={"dates": date_str}, timeout=DEFAULT_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.warning(f"ESPN odds request failed: {exc}")
        return {}
    except json.JSONDecodeError as exc:
        logger.warning(f"ESPN odds returned invalid JSON: {exc}")
        return {}

    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return _parse_odds_cache(data)


def _parse_odds_cache(data: dict) -> dict[str, AmericanOdds]:
    def _close_odds(side: dict | None) -> int | None:
        """Extract a single American-odds integer from moneyline.<side>.close."""
        if not isinstance(side, dict):
            return None
        close = side.get("close")
        if not isinstance(close, dict):
            return None
        raw = close.get("odds")
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    out: dict[str, AmericanOdds] = {}
    for e in data.get("events", []):
        eid = str(e.get("id", ""))
        comps = e.get("competitions", [{}])[0]
        odds = comps.get("odds", [])
        if not odds or odds[0] is None:
            continue
        o = odds[0]
        ml = o.get("moneyline", {})
        home = _close_odds(ml.get("home"))
        draw_ml = _close_odds(ml.get("draw"))
        away_ml = _close_odds(ml.get("away"))
        # Fallback: some endpoints use drawOdds flat at the top level.
        if draw_ml is None:
            draw_ml = _close_odds({"close": o.get("drawOdds", {})})
        total = o.get("total", {})
        over_odds = _close_odds(total.get("over")) if isinstance(total, dict) else None
        under_odds = _close_odds(total.get("under")) if isinstance(total, dict) else None
        out[eid] = AmericanOdds(
            home=home,
            draw=draw_ml,
            away=away_ml,
            over_under=o.get("overUnder"),
            over_odds=over_odds,
            under_odds=under_odds,
            provider=o.get("provider", {}).get("name") if isinstance(o.get("provider"), dict) else None,
        )
    return out


def market_probs(odds: AmericanOdds) -> tuple[float, float, float, float] | None:
    """Convert AmericanOdds to (p_home, p_draw, p_away, expected_total).

    Returns None if home/away odds are missing.

    Expected total is derived from over/under when both legs are present.
    """
    if odds.home is None or odds.away is None:
        return None
    p_h = american_to_implied(odds.home) or 0.0
    p_d = american_to_implied(odds.draw) or 0.0
    p_a = american_to_implied(odds.away) or 0.0
    p_h, p_d, p_a = _devig(p_h, p_d, p_a)
    # Expected total: assume over and under are de-vigged mirror images.
    # p_over = odds_implied(over_odds) / (over + under)
    expected_total: float | None = None
    if odds.over_odds is not None and odds.under_odds is not None and odds.over_under is not None:
        p_over = american_to_implied(odds.over_odds) or 0.0
        p_under = american_to_implied(odds.under_odds) or 0.0
        s = p_over + p_under
        if s > 0:
            p_over_fair = p_over / s
            # E[total] for a Poisson-like distribution with P(over)=p_over_fair
            # at threshold T: p_over_fair = 1 - poisson_cdf(T)
            # Solve for mu by inverting the CDF iteratively.
            import math
            from math import exp, factorial

            def poisson_cdf(mu: float, k: int) -> float:
                return sum(mu**i * exp(-mu) / factorial(i) for i in range(k + 1))

            target = odds.over_under
            # Binary search for mu
            lo, hi = 0.0, 10.0
            for _ in range(80):
                mid = (lo + hi) / 2
                if poisson_cdf(mid, int(target)) > 1 - p_over_fair:
                    lo = mid
                else:
                    hi = mid
            expected_total = (lo + hi) / 2
    return p_h, p_d, p_a, expected_total or 0.0


if __name__ == "__main__":
    odds = fetch_odds()
    print(f"Fetched odds for {len(odds)} events")
    for eid, o in odds.items():
        p = market_probs(o)
        if p:
            ph, pd, pa, et = p
            print(f"  {eid}: home={o.home:+d} draw={o.draw:+d} away={o.away:+d}  O/U={o.over_under} → P(h/d/a)={ph:.0%}/{pd:.0%}/{pa:.0%} E[total]={et:.2f}")
