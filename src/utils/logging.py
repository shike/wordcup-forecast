"""Logging configuration using loguru."""
from __future__ import annotations

import sys

from loguru import logger

from src.utils.config import config


def setup_logging(level: str = "INFO") -> None:
    """Configure loguru to stdout with a clean format."""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <level>{message}</level>",
        level=level,
    )
    config.output_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(config.output_dir / "predict.log"),
        rotation="5 MB",
        level=level,
    )
