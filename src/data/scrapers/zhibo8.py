"""Zhibo8 (Qiumibao) hot-news scraper.

Fetches the last 24 hours of Chinese sports headlines from Zhibo8's public
JSON endpoint. Useful for picking up pre-match news, injuries, and lineup
rumours that may not appear in English-language sources.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import requests
from loguru import logger

from src.utils.config import config


QIUMIBAO_BASE = "https://s.qiumibao.com"
HOT_NEWS_PATH = "/json/hot/24hours.htm"

# Sports categories we care about for football prediction.
FOOTBALL_TYPES = {"zuqiu", "football", "soccer"}


@dataclass(frozen=True)
class NewsItem:
    id: str
    title: str
    short_title: str
    news_type: str
    created_at: str
    url: str
    thumbnail: str | None
    source: str
    comment_id: str | None


def _cache_path() -> Path:
    return config.api_cache / "zhibo8_hot_24h.json"


def _parse_item(raw: dict) -> NewsItem | None:
    """Convert a single Qiumibao news entry into a typed NewsItem."""
    filename = raw.get("filename") or raw.get("way") or ""
    if not filename:
        return None
    url = raw.get("url", "")
    if url and not url.startswith(("http:", "https:")):
        url = urljoin("https://www.zhibo8.cc/", url)
    return NewsItem(
        id=str(raw.get("m_uid", filename)),
        title=raw.get("title", ""),
        short_title=raw.get("shortTitle", ""),
        news_type=str(raw.get("type", "")).lower(),
        created_at=raw.get("createtime", ""),
        url=url,
        thumbnail=raw.get("thumbnail") or None,
        source=raw.get("from_name", "直播吧"),
        comment_id=raw.get("pinglun") or None,
    )


def fetch_hot_news(
    use_cache: bool = True,
    cache_ttl_seconds: int = 300,
) -> list[NewsItem]:
    """Fetch the last 24 hours of hot news from Zhibo8.

    Args:
        use_cache: If True, return a cached response when it is fresh.
        cache_ttl_seconds: How long to keep a cached response (default 5 min).
    """
    cache = _cache_path()
    if use_cache and cache.exists():
        age = datetime.now().timestamp() - cache.stat().st_mtime
        if age < cache_ttl_seconds:
            try:
                raw = json.loads(cache.read_text(encoding="utf-8"))
                return [_parse_item(n) for n in raw.get("news", []) if _parse_item(n)]
            except Exception:
                pass

    url = f"{QIUMIBAO_BASE}{HOT_NEWS_PATH}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.warning(f"Zhibo8 hot news request failed: {exc}")
        return []
    except json.JSONDecodeError as exc:
        logger.warning(f"Zhibo8 hot news returned invalid JSON: {exc}")
        return []

    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    news = [_parse_item(n) for n in data.get("news", [])]
    valid = [n for n in news if n]
    logger.info(f"Fetched {len(valid)} Zhibo8 hot news items")
    return valid


def fetch_football_news(**kwargs) -> list[NewsItem]:
    """Return only football-related items from the Zhibo8 hot list."""
    return [n for n in fetch_hot_news(**kwargs) if n.news_type in FOOTBALL_TYPES]


def yield_recent_headlines(
    hours: int = 24,
    football_only: bool = True,
) -> Iterable[NewsItem]:
    """Yield news items published within the last N hours.

    This is a convenience wrapper around fetch_hot_news / fetch_football_news
    that applies a client-side time filter, since the upstream endpoint always
    returns the last 24 hours.
    """
    now = datetime.now(timezone.utc)
    items = fetch_football_news() if football_only else fetch_hot_news()
    for item in items:
        if not item.created_at:
            continue
        try:
            published = datetime.fromisoformat(item.created_at)
            if (now - published).total_seconds() <= hours * 3600:
                yield item
        except Exception:
            continue


if __name__ == "__main__":
    items = fetch_football_news()
    print(f"{len(items)} football items")
    for item in items[:10]:
        print(f"[{item.news_type}] {item.created_at} {item.title}")
        print(f"    {item.url}")
