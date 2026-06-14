# DATA HANDBOOK

Each data source the World Cup prediction pipeline uses, what it
covers, what its known gaps are, and how to add it.

Last reviewed: 2026-06-14.

---

## 1. martj42 / international_results CSV (international `A` matches)

- **Source**: `https://raw.githubusercontent.com/martj42/international_results/master/results.csv` (CC0 / public domain)
- **Local cache**: `data/external/international_results.csv`
- **Ingestor**: `src/data/scrapers/martj42.py`
- **Range**: 1872 → present; ~46,000 matches globally
- **Coverage for World Cup teams**: ~9,884 matches ingested
- **Columns**: date, home_team, away_team, home_score, away_score, tournament, city, neutral
- **Strengths**:
  - Multi-decade historical coverage
  - All major football federations
  - Used for long-term ELO and team-quality priors
- **Known gaps**:
  - No xG (Goals are used as xG proxy via `xg_proxy.py` after r2)
  - No player-level data
  - No shot / corner / foul / cards data
  - Resolution: match level only

## 2. StatsBomb Open Data (event-level)

- **Source**: `https://github.com/statsbomb/open-data` (free for non-commercial)
- **Local cache**: `缓存/statsbomb/events_*.json`
- **Ingestor**: `src/data/scrapers/statsbomb.py` (matches) + `src/data/scrapers/statsbomb_features.py` (events)
- **Range**: 2018 + 2022 FIFA World Cup = 128 matches, ~4000 events per match
- **Columns (per event)**: timestamp, period, type, possession, location, player, team, plus type-specific sub-objects (`shot.statsbomb_xg`, `pass.outcome`, `pressure`, `duel.outcome`, etc.)
- **Strengths**:
  - Only open source of true xG for World Cup
  - Player-level pass / shot / pressure data
  - Possession duration via possession counter
  - Set-piece detection via `play_pattern`
- **Known gaps**:
  - Only 128 matches (2018 + 2022 WC)
  - No yellow/red cards in the WC 2018/2022 release (they're in the 360 extension only)
  - StatsBomb 360 freeze-frame data not yet ingested (would require `data/three-sixty/{id}.json` per match)

## 3. Dongqiudi (懂球帝) public scoreboard

- **Source**: `https://api.dongqiudi.com/data/tab/important?start=<Beijing-time>` (no key)
- **Local cache**: `缓存/dongqiudi_important_*.json`
- **Ingestor**: `src/data/scrapers/dongqiudi.py`
- **Range**: Last 49 important matches (rolling 24-72h window)
- **Strengths**:
  - Chinese team names (no need to translate)
  - Real-time 2026 WC fixtures
  - Includes in-progress matches with halftime scores
  - 0 cost, 0 key
- **Known gaps**:
  - 49-match window doesn't reach CIV, CUW, and other small teams
  - No xG field
  - No per-player data

## 4. Zhibo8 (直播吧) hot news feed

- **Source**: `https://s.qiumibao.com/json/hot/24hours.htm` (no key)
- **Local cache**: `缓存/API响应/zhibo8_hot_24h.json` (5 min TTL)
- **Ingestor**: `src/data/scrapers/zhibo8.py`
- **Range**: Last 24h, ~1,300 news items
- **Strengths**:
  - Chinese sports news including injuries, lineup changes, transfer rumors
  - Used for pre-match news in PPT slide 4
- **Known gaps**:
  - No per-match drill-down (only the 24h top-N)
  - To get per-match news we'd need to scrape individual match pages

## 5. ESPN public scoreboard (fixtures, results, odds)

- **Source**: `https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=YYYYMMDD` (no key)
- **Local cache**: `缓存/API响应/赛程_espn_*.json`
- **Ingestor**: `src/data/fixtures.py` (fixtures) + `src/data/scrapers/espn_odds.py` (odds)
- **Strengths**:
  - Real-time fixtures, results, and DraftKings odds
  - 1X2 + over/under (O/U line) markets
  - Livescore with halftime / in-progress states
  - Venue, broadcast, attendance data
- **Known gaps**:
  - `/summary` endpoint does NOT include actual lineups or injuries
  - No player-level data
  - Network flaky from some regions (Cloudflare occasionally 500s)

## 6. Wikipedia REST API (free, no key)

- **Source**: `https://en.wikipedia.org/w/api.php?action=parse&page=...&prop=wikitext`
- **Strengths**: Free, no auth, comprehensive
- **Known gaps**:
  - Single-mutation-rate-limit (200 req/s/IP)
  - Content is in wikitext, needs parsing
  - For lineups we need to wait for the post-match lineup page; pre-game
    the page doesn't have the 11 yet
  - Tried: did not yield enough reliable content for 5 tonight matches

## 7. Manual-seed (6-match hand-built CIV/CUW)

- **Source**: `src/data/seed_underdog.py`
- **Coverage**: 6 matches each for Ivory Coast and Curaçao, drawn from public knowledge of AFCON 2025 qualifiers, 2026 WC qualifiers, friendlies
- **Strengths**: Fills the gap for teams with no data in the warehouse
- **Known gaps**:
  - 6 matches against minnows (e.g. SLV/PAN/GUA/HON for CUW)
  - Hand-built: not real-time, needs manual updating

## 8. xG Proxy (goals as xG fallback)

- **Source**: `src/data/scrapers/xg_proxy.py`
- **What it does**: Copies `home_goals` → `home_xg` and `away_goals` → `away_xg` for matches without real xG data
- **Strengths**: Fills 9,893 / 9,896 matches with xG proxy
- **Known gaps**:
  - Goals and xG are correlated but not identical
  - Goals tend to over-estimate true xG in low-quality shots games and under-estimate in high-shot-quality games

---

## Tables inventory

The SQLite warehouse lives at `缓存/worldcup_forecast.db`.

| Table | Rows | Source |
|-------|------|--------|
| matches | 9,896 | martj42 + Dongqiudi + StatsBomb + manual-seed |
| match_player_stats | 3,783 | StatsBomb events |
| xg_events | 3,154 | StatsBomb shot-level |
| elo_history | 19,721 | martj42 computed |
| teams | 32+ | project seed (data/teams.json) |
| ingestion_log | per-source timestamps | project |

## Adding a new data source

1. Write a scraper under `src/data/scrapers/`
2. Match the existing `fetch_*` / `load_*` interface so it slots into `ingest.py`
3. Save to a sub-table in the warehouse with explicit `source` label
4. Update `FeatureBuilder._aggregate_form` if the new source has signals
5. Document it in this handbook

## Known unresolvable gaps (no key)

| Data | Why |
|------|-----|
| Player ratings (JRs / SS) | Requires Hupu / Dongqiudi app reverse-engineering |
| FIFA official xG | Requires FIFA Data API key |
| Bet365 / Pinnacle sharp odds | Requires paid odds API |
| Historical Asian handicap / closing line | Requires paid odds API |
| Real-time in-game xG | Requires broadcast data (StatsPerform / Opta partnership) |
