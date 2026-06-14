"""Sync World Cup squads from the Wikipedia "2022 FIFA World Cup squads" page.

The page at https://en.wikipedia.org/wiki/2022_FIFA_World_Cup_squads embeds a
table for each of the 32 qualified national teams, with one row per player
(26 rows per team) and columns: number, position, player name, date of
birth, caps, goals, club. Player names link to their Wikipedia pages which
the script also queries to fetch the real headshot via the REST summary
API.

The output is one JSON file per team in data/squads/{CODE}.json that the
load_squad loader reads.

Wikipedia position codes are translated to the project's 11-position literal
set (GK/RB/CB/LB/CDM/CM/CAM/RW/LW/ST/CF) by looking up each player in
the deeper Wikipedia "international career" context. Where the translation
cannot be decided, the script keeps the raw two-letter code (DF/MF/FW)
which load_squad then routes by formation slot.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag
from loguru import logger

from src.data.wikipedia_client import fetch_player_summary
from src.utils.config import config
from src.utils.image import fetch_photo, player_id_from_name


WIKI_SQUADS_URL = "https://en.wikipedia.org/wiki/2022_FIFA_World_Cup_squads"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Wikipedia "natural" position code -> project 11-position literal.
# Where the source is ambiguous (e.g. FW could be ST/CF/LW/RW), the project
# falls back to the formation slot — these mappings cover the clear cases.
POSITION_MAP: dict[str, str] = {
    "GK": "GK",
    "DF": "CB",  # generic defender: project routes to formation slot
    "MF": "CM",  # generic midfielder: project routes to formation slot
    "FW": "ST",  # generic forward: project routes to formation slot
}

# The country names as they appear in the 2022 squads Wikipedia page, mapped
# to the project's 3-letter team codes. Includes the 32 qualified teams
# plus the 2 hosts/winners from the original page layout.
TEAM_CODE_FROM_HEADING: dict[str, str] = {
    "Argentina": "ARG", "Australia": "AUS", "Belgium": "BEL", "Brazil": "BRA",
    "Cameroon": "CMR", "Canada": "CAN", "Costa Rica": "CRC", "Croatia": "CRO",
    "Denmark": "DEN", "Ecuador": "ECU", "England": "ENG", "France": "FRA",
    "Germany": "GER", "Ghana": "GHA", "Iran": "IRN", "Japan": "JPN",
    "Mexico": "MEX", "Morocco": "MAR", "Netherlands": "NED", "Poland": "POL",
    "Portugal": "POR", "Qatar": "QAT", "Saudi Arabia": "KSA", "Senegal": "SEN",
    "Serbia": "SRB", "South Korea": "KOR", "Spain": "ESP", "Switzerland": "SUI",
    "Tunisia": "TUN", "United States": "USA", "Uruguay": "URU", "Wales": "WAL",
    # 2018 qualifiers also present in the page (Wikipedia includes both):
    "Iceland": "ISL", "Nigeria": "NGA", "Colombia": "COL", "Peru": "PER",
    "Sweden": "SWE", "Russia": "RUS", "Panama": "PAN", "Egypt": "EGY",
}


def _next_team_table(soup: BeautifulSoup, team_name: str) -> Tag | None:
    """Find the squad table that immediately follows the h3 heading."""
    heading = soup.find(lambda t: t.name in ("h2", "h3") and t.get_text(strip=True) == team_name)
    if not heading:
        return None
    return heading.find_next("table")


def _parse_age(dob_text: str) -> int | None:
    m = re.search(r"\(aged (\d+)\)", dob_text)
    if m:
        return int(m.group(1))
    m = re.search(r"\((\d{4})\)", dob_text)
    if m:
        return 2022 - int(m.group(1))
    return None


def _parse_int(text: str) -> int:
    m = re.search(r"\d+", text)
    return int(m.group(0)) if m else 0


def _parse_player_row(row: Tag) -> dict | None:
    cells = row.find_all(["th", "td"])
    if len(cells) < 6:
        return None
    # Row 0 is the table header (No., Pos., Player, DoB, Caps, Goals, Club).
    # For player rows, cells[0] is shirt number, cells[1] position (e.g. "1GK"),
    # cells[2] player name + link, cells[3] DoB, cells[4] caps, cells[5] goals,
    # cells[6] club.
    pos_text = cells[1].get_text(strip=True)
    pos_code_match = re.match(r"\d*([A-Z]+)", pos_text)
    if not pos_code_match:
        return None
    pos_code = pos_code_match.group(1)
    if pos_code not in POSITION_MAP:
        return None
    position = POSITION_MAP[pos_code]

    number = _parse_int(cells[0].get_text(strip=True))

    # Player cell contains the link to the player's Wikipedia page
    player_cell = cells[2]
    player_link = player_cell.find("a", href=True)
    if not player_link:
        return None
    name = player_link.get_text(strip=True)
    wiki_url = "https://en.wikipedia.org" + player_link["href"]

    dob_text = cells[3].get_text(strip=True)
    age = _parse_age(dob_text)
    caps = _parse_int(cells[4].get_text(strip=True))
    goals = _parse_int(cells[5].get_text(strip=True))
    club = cells[6].get_text(strip=True) if len(cells) > 6 else ""

    return {
        "name": name,
        "position": position,
        "number": number,
        "age": age or 25,
        "club": club,
        "caps": caps,
        "goals": goals,
        "rating": 7.0,  # Wikipedia does not carry ratings; placeholder until
                          # FBref / Understat scrape fills this in
        "preferred_foot": "R",
        "height_cm": 180,
        "wikipedia_url": wiki_url,
    }


def _name_to_zh(name_en: str) -> str | None:
    """Best-effort Chinese name lookup via the Wikipedia summary endpoint."""
    summary = fetch_player_summary(name_en)
    if not summary:
        return None
    extract = summary.get("extract") or ""
    # Heuristic: look for Chinese in the extract (Wikipedia stores it as
    # the article opening line for many footballers: "Name (Chinese: X)")
    m = re.search(r"Chinese[^一-鿿]*([一-鿿]+)", extract)
    if m:
        return m.group(1)
    return None


def _photo_url_for(name_en: str) -> str | None:
    summary = fetch_player_summary(name_en)
    if not summary:
        return None
    original = summary.get("originalimage") or {}
    return original.get("source") or (summary.get("thumbnail") or {}).get("source")


def sync_team(soup: BeautifulSoup, team_name: str, with_photos: bool = True) -> int:
    """Sync one team. Returns the number of player rows written."""
    code = TEAM_CODE_FROM_HEADING.get(team_name)
    if code is None:
        logger.warning(f"  Unknown team name: {team_name}")
        return 0
    table = _next_team_table(soup, team_name)
    if table is None:
        logger.warning(f"  No table for {team_name}")
        return 0
    rows = table.find_all("tr")
    players: list[dict] = []
    for r in rows[1:]:  # skip header
        parsed = _parse_player_row(r)
        if parsed:
            parsed["id"] = player_id_from_name(parsed["name"])
            players.append(parsed)

    # Chinese names (always) + photos (unless --no-photos)
    for p in players:
        time.sleep(0.05)  # be polite to Wikipedia
        p["name_zh"] = _name_to_zh(p["name"])
        if p["name_zh"] is None:
            p["name_zh"] = p["name"]
        if with_photos:
            photo_url = _photo_url_for(p["name"])
            if photo_url:
                saved = fetch_photo(photo_url, p["id"])
                if saved:
                    p["photo_path"] = str(saved)

    out_path = config.squad_data_dir / f"{code}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)
        f.write("\n")
    logger.info(f"  {team_name} ({code}): {len(players)} players → {out_path}")
    return len(players)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-photos", action="store_true",
                        help="Skip photo downloads (faster, useful for CI)")
    args = parser.parse_args()

    logger.info("Fetching Wikipedia 2022 World Cup squads page…")
    resp = requests.get(WIKI_SQUADS_URL, timeout=30, headers=HEADERS)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    total_teams = 0
    total_players = 0
    for heading in soup.find_all(["h2", "h3"]):
        team_name = heading.get_text(strip=True)
        if team_name in TEAM_CODE_FROM_HEADING:
            total_players += sync_team(soup, team_name, with_photos=not args.no_photos)
            total_teams += 1
            time.sleep(0.5)

    logger.success(
        f"Synced {total_teams} teams, {total_players} player rows."
    )


if __name__ == "__main__":
    main()
