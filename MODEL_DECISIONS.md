# MODEL DECISIONS

Chronological log of every meaningful model change.

---

## 2026-06-14 — Initial Dixon-Coles scaffold

- `λ_a = μ_league × α_a × β_b × quality_a`
- `α, β` Bayesian-blend with ELO prior (weight 5)
- `quality = clamp(0.95, 1.05, 0.25 × xG/goals)`
- Matrix 8×8
- Goals used as xG proxy for non-StatsBomb matches
- Confidence: 4 fields; if any is real → data is real

## 2026-06-14 — Manual-seed for CIV and CUW

- 6 hand-built matches each for Ivory Coast and Curaçao
- Source: `data/seed_underdog.py` (AFCON 2025 qualifiers, 2026 WC qualifiers, friendlies)
- Effect: lifts data-quality score from 1/5 → 5/5 for these teams

## 2026-06-14 — xG proxy backfill

- `src/data/scrapers/xg_proxy.py`
- Copies `home_goals` → `home_xg`, same for away
- 9,893 of 9,896 matches now have xG field
- Rationale: over 0 goal games, xG ~ goals in expectation

## 2026-06-14 — StatsBomb event feature extraction

- `src/data/scrapers/statsbomb_features.py`
- 128 WC matches × ~30 events per team → 3,783 player stats
- 3,200+ shot-level xG events
- 128 match summary sidecar JSONs (possession %, pressures, set-piece share)
- Uses canonical `HOME-AWAY-DATE` IDs to match `statsbomb.py` ingest

## 2026-06-14 — First nightly predictions (5 matches)

- All 5 used model xG only
- Issues:
  - All picks were 1-1 / 0-1 — distribution too narrow
  - NED vs JPN picked Japan (counter-intuitive)
  - GER-CUW lambda too close to 1-1 (poor sample)

## 2026-06-14 — Adjustments rewrite

- Original `apply_adjustments` shifted probability ±15% per factor
- New version: shift bounded to ±5%, factor derives from qualitative
- Goal: stop the model from overreacting to small lambda differentials

## 2026-06-14 — Quality factor widened to ±10%

- Original `_xg_quality_factor` clamped at ±5%
- Widened to ±10% so true xG actually moves expected goals
- Re-asserted bounded range in `_xg_quality_factor` later (±5%)

## 2026-06-14 — α/β soft caps tightened

- Original `[0.5, 2.0]` → `[0.4, 2.5]` to allow wider spread
- Settled at `[0.55, 1.8]` to prevent single-match blowouts from dominating

## 2026-06-14 — Sample-size shrinkage for raw α/β

- New layer: 12-game prior shrinking raw α/β toward 1.0
- Protects against extreme estimates from small samples (e.g. 6-game seeds)
- Combined with ELO prior (25-game effective) for strong ELO influence

## 2026-06-14 — Manual-seed down-weighting

- 30% weight for `manual-seed` source matches
- Rationale: 6 matches vs minnows is not representative of FIFA World Cup level

## 2026-06-14 — Pick-aware predicted_score

- `predicted_score_for(pick)` returns most likely score **in the
  pick's direction** rather than the overall mode
- Avoids the 1-1 default when the model picks a decisive winner

## 2026-06-14 — Matrix widened to 11×11

- Score matrix now 0-10 goals per side
- Captures 5-0 / 6-1 type outcomes instead of capping at 7-0

## 2026-06-14 — Dixon-Coles ρ = -0.07

- Tuned from -0.08 to -0.07 to slightly reduce 1-1 / 0-0 inflation
- Standard academic range: -0.05 to -0.15

## 2026-06-14 — Time-decay feature aggregation

- Half-life 720 days (~2 years) for recent-form weighting
- 4 years old: 25% weight
- 1 year old: 71% weight
- 6 months old: 94% weight
- Effect: GER xG 2.04 → 2.13 (more recent weighted)
- Effect: JPN xGA 0.98 → 0.89 (more recent weighted)

## 2026-06-14 — Market-driven prediction (real DraftKings odds)

- `src/data/scrapers/espn_odds.py` fetches DraftKings via ESPN public API
- `src/predict/market.py` translates American odds to fair probabilities
  using overround de-vig
- Tonight 5 matches: 4 with real odds (91/6/3 for GER-CUW), 1 with ELO
  fallback (AUS-TUR, in progress)
- O/U line + Poisson-CDF inversion → expected total

## 2026-06-14 — Market-aware Poisson

- `predict_market_aware(..., p_home_market, expected_total_market, market_weight)`
- Blends xG-driven lambda with market-implied lambda
- `market_weight = 0.5` is the default
- 1X2 probabilities are anchored to market, not derived from Poisson

## 2026-06-14 — Hourly odds movement monitor

- `scripts/odds_monitor.py` records snapshots to `缓存/odds_movement.jsonl`
- Supports `--diff` to show line moves since the last snapshot
- Will be run periodically to track market sentiment changes

---

## Pending / open questions

1. **CIV / CUW 数据真实化**: Hand-built seeds need replacement with FIFA
   official data (requires key). When CIV plays their first game, real
   data will start populating.
2. **球员评分**: Hupu / Dongqiudi app required.
3. **StatsBomb 360 freeze-frame**: Not yet ingested; would enable
   custom xG model on top of StatsBomb's official xG.
4. **多源化赔率**: Most public odds APIs require keys. ESPN +
   DraftKings is the only no-key reliable source.
5. **赛前阵容实时抓取**: Dongqiudi pages have lineups but require
   browser scraping. Hard to do without Selenium / playwright.
