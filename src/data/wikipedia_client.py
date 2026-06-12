"""Wikipedia client for player bio and photo URLs.

Uses the `wikipedia` package which wraps the MediaWiki API.  All calls are
guarded so that a network failure just returns None — the PPT will then fall
back to text-only player cards.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import requests
from loguru import logger

from src.utils.config import config
from src.utils.models import Player
from src.utils.image import cached_photo_exists, fetch_photo, player_id_from_name


WIKIPEDIA_REST = "https://en.wikipedia.org/api/rest_v1"
HEADERS = {"User-Agent": "wordcup-forecast/1.0 (contact: example@example.com)"}


def _summary_cache_path(name: str) -> Path:
    safe = re.sub(r"[^a-z0-9一-鿿]+", "_", name.lower())[:60]
    return config.api_cache / f"球员摘要_{safe}.json"


def fetch_player_summary(name: str) -> dict[str, Any] | None:
    """Fetch a Wikipedia page summary for a player (bio, image, position)."""
    cache = _summary_cache_path(name)
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass
    try:
        url = f"{WIKIPEDIA_REST}/page/summary/{name.replace(' ', '_')}"
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code != 200:
            return None
        data = resp.json()
        cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data
    except Exception as e:
        logger.debug(f"Wikipedia summary fetch failed for {name}: {e}")
        return None


def extract_photo_url(summary: dict[str, Any]) -> str | None:
    """Best-effort extraction of a portrait photo URL from a summary."""
    if not summary:
        return None
    if "thumbnail" in summary and "source" in summary["thumbnail"]:
        return summary["thumbnail"]["source"]
    if "originalimage" in summary and "source" in summary["originalimage"]:
        return summary["originalimage"]["source"]
    return None


def augment_player_with_wiki(player: Player) -> Player:
    """Fill in missing fields (photo_path, name_zh) from Wikipedia if possible."""
    if player.photo_path and cached_photo_exists(player.id):
        return player
    summary = fetch_player_summary(player.name)
    if not summary:
        return player

    photo_url = extract_photo_url(summary)
    if photo_url and not player.photo_path:
        local = fetch_photo(photo_url, player.id)
        if local is not None:
            player.photo_path = str(local)

    if not player.wikipedia_url and "content_urls" in summary:
        try:
            player.wikipedia_url = summary["content_urls"]["desktop"]["page"]
        except KeyError:
            pass

    return player


def batch_augment_squad(players: list[Player], max_workers: int = 4) -> list[Player]:
    """Augment many players. Uses sequential IO to stay within the rate limit."""
    augmented: list[Player] = []
    for p in players:
        try:
            augmented.append(augment_player_with_wiki(p))
        except Exception as e:
            logger.debug(f"Augment failed for {p.name}: {e}")
            augmented.append(p)
    return augmented
