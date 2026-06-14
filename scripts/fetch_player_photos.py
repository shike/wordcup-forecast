"""Fetch real player headshots from Wikipedia and wire them into the squad
seed files.

For every player in data/squads/{CODE}.json:
1. If the player already has a working photo_path on disk, skip.
2. Otherwise look up the player on Wikipedia (English) and download the
   `thumbnail` image from the page summary.
3. Save the JPEG into 缓存/球员照片/{player_id}.jpg and update the
   player's `photo_path` in the squad JSON.

Run with:

    python -m scripts.fetch_player_photos
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests
from loguru import logger

from src.data.wikipedia_client import fetch_player_summary
from src.utils.config import config
from src.utils.image import cached_photo_exists, fetch_photo, player_id_from_name


HEADERS = {"User-Agent": "wordcup-forecast/1.0 (contact: example@example.com)"}


def _photo_url_for(name: str) -> str | None:
    """Look up a player's Wikipedia thumbnail URL by their page summary."""
    summary = fetch_player_summary(name)
    if not summary:
        return None
    thumb = summary.get("thumbnail") or {}
    return thumb.get("source")


def main() -> None:
    squad_dir = config.squad_data_dir
    total_players = 0
    total_fetched = 0
    total_skipped = 0
    total_failed: list[tuple[str, str]] = []

    for squad_file in sorted(squad_dir.glob("*.json")):
        team_code = squad_file.stem
        with open(squad_file, encoding="utf-8") as f:
            players = json.load(f)

        updated = False
        for player in players:
            name = player.get("name", "")
            if not name:
                continue
            total_players += 1
            pid = player.get("id") or player_id_from_name(name)
            player["id"] = pid

            existing = player.get("photo_path")
            if existing and Path(existing).exists():
                total_skipped += 1
                continue

            url = _photo_url_for(name)
            if not url:
                total_failed.append((team_code, name))
                continue

            saved = fetch_photo(url, pid)
            if saved is None:
                total_failed.append((team_code, name))
                continue

            player["photo_path"] = str(saved)
            updated = True
            total_fetched += 1
            logger.info(f"  {team_code} {name} → {saved}")

        if updated:
            with open(squad_file, "w", encoding="utf-8") as f:
                json.dump(players, f, ensure_ascii=False, indent=2)
                f.write("\n")

    logger.success(
        f"Done. {total_fetched} fetched, {total_skipped} skipped, "
        f"{len(total_failed)} failed out of {total_players} players."
    )
    if total_failed:
        logger.info("Failures (team, player):")
        for team_code, name in total_failed[:30]:
            logger.info(f"  {team_code} {name}")


if __name__ == "__main__":
    main()
