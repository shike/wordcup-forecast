"""Configuration loaded from environment and .env file."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Config:
    football_data_api_key: str = os.getenv("FOOTBALL_DATA_API_KEY", "")
    jisu_api_key: str = os.getenv("JISU_API_KEY", "")
    offline_mode: bool = os.getenv("OFFLINE_MODE", "false").lower() == "true"
    output_dir: Path = PROJECT_ROOT / os.getenv("OUTPUT_DIR", "./输出")
    cache_dir: Path = PROJECT_ROOT / os.getenv("CACHE_DIR", "./缓存")
    default_lang: str = os.getenv("DEFAULT_LANG", "bilingual")

    player_photo_cache: Path = PROJECT_ROOT / "缓存" / "球员照片"
    api_cache: Path = PROJECT_ROOT / "缓存" / "API响应"
    squad_data_dir: Path = PROJECT_ROOT / "data" / "squads"
    assets_dir: Path = PROJECT_ROOT / "assets"
    team_logos_dir: Path = PROJECT_ROOT / "assets" / "team_logos"
    fonts_dir: Path = PROJECT_ROOT / "assets" / "fonts"

    historical_matches_csv: Path = PROJECT_ROOT / "data" / "historical_matches.csv"
    formations_json: Path = PROJECT_ROOT / "data" / "formations.json"
    teams_json: Path = PROJECT_ROOT / "data" / "teams.json"

    @classmethod
    def ensure_dirs(cls) -> None:
        for d in (
            cls.output_dir,
            cls.cache_dir,
            cls.player_photo_cache,
            cls.api_cache,
            cls.squad_data_dir,
            cls.assets_dir,
            cls.team_logos_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


config = Config()
config.ensure_dirs()
