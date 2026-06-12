"""Manual adjustment interface for qualitative factors.

CLI tool that lets the user override model inputs without writing code.
"""
from __future__ import annotations

from loguru import logger

from src.utils.models import QualitativeFactors, TeamStats


def manual_override_stats(stats: TeamStats) -> TeamStats:
    """Prompt the user to override any of the team stats. Returns a new object."""
    logger.info("Press Enter to keep default value.")
    fields = [
        ("goals_per_game", "场均进球"),
        ("conceded_per_game", "场均失球"),
        ("xg_per_game", "xG"),
        ("xga_per_game", "xGA"),
        ("clean_sheet_rate", "零封率"),
        ("key_passes_per_game", "关键传球"),
        ("shot_accuracy", "射门精度"),
        ("tackles_per_game", "抢断"),
        ("interceptions_per_game", "拦截"),
    ]
    updates: dict[str, float] = {}
    for field, label in fields:
        current = getattr(stats, field)
        try:
            raw = input(f"  {label} [{current}]: ").strip()
        except EOFError:
            return stats
        if raw:
            try:
                updates[field] = float(raw)
            except ValueError:
                logger.warning(f"Invalid value for {label}, keeping default")
    if not updates:
        return stats
    return stats.model_copy(update=updates)


def manual_override_qualitative(qual: QualitativeFactors) -> QualitativeFactors:
    logger.info("Press Enter to keep default value (1-10).")
    fields = [
        ("tactical", "战术"),
        ("experience", "大赛经验"),
        ("psychology", "心理因素"),
        ("venue_factor", "场地因素"),
        ("schedule", "赛程密度"),
    ]
    updates: dict[str, float] = {}
    for field, label in fields:
        current = getattr(qual, field)
        try:
            raw = input(f"  {label} [{current}]: ").strip()
        except EOFError:
            return qual
        if raw:
            try:
                v = float(raw)
                updates[field] = max(1.0, min(10.0, v))
            except ValueError:
                pass
    if not updates:
        return qual
    return qual.model_copy(update=updates)
