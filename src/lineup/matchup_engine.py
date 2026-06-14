"""Generate 1v1 player matchups for the key page.

Picks duels strictly from players who actually play the relevant position. If
a slot cannot be filled because no player in the lineup occupies that
position, the slot is simply skipped — we never invent a position match.
"""
from __future__ import annotations

from loguru import logger

from src.utils.models import Lineup, Matchup, Player


def _best_at(players: list[Player], positions: list[str], prefer_rating: bool = True) -> Player | None:
    candidates = [p for p in players if p.position in positions]
    if not candidates:
        return None
    if prefer_rating:
        return max(candidates, key=lambda p: (p.rating, p.caps))
    return max(candidates, key=lambda p: p.caps)


def _pair(label_zh: str, label_en: str, a: Player, b: Player) -> Matchup:
    return Matchup(
        title_zh=label_zh,
        title_en=label_en,
        player_a=a,
        player_b=b,
        stat_pairs=[
            ("评分", "Rating", f"{a.rating:.1f}", f"{b.rating:.1f}"),
            ("年龄", "Age", f"{a.age}", f"{b.age}"),
            ("身高", "Height", f"{a.height_cm}cm", f"{b.height_cm}cm"),
            ("国家队出场", "Caps", f"{a.caps}", f"{b.caps}"),
            ("进球", "Goals", f"{a.goals}", f"{b.goals}"),
            ("惯用脚", "Foot", a.preferred_foot, b.preferred_foot),
        ],
    )


def generate_matchups(
    lineup_a: Lineup, lineup_b: Lineup, code_a: str, code_b: str
) -> list[Matchup]:
    matchups: list[Matchup] = []
    pl_a = lineup_a.players
    pl_b = lineup_b.players

    # Striker (A) vs central defender (B)
    sa = _best_at(pl_a, ["ST", "CF", "RW", "LW"])
    cb = _best_at(pl_b, ["CB"])
    if sa and cb:
        matchups.append(
            _pair("箭头对决 · 锋线尖刀 vs 中后卫", "Star Striker vs Centre-Back", sa, cb)
        )

    # Creative midfielder (A) vs defensive midfielder (B)
    cam = _best_at(pl_a, ["CAM", "CM"])
    cdm = _best_at(pl_b, ["CDM", "CM"])
    if cam and cdm:
        matchups.append(
            _pair("中场大脑 · 创造者 vs 清道夫", "Playmaker vs Anchor", cam, cdm)
        )

    # Speed winger (A) vs fullback (B) — only when the formation actually has
    # players in those positions.
    winger = _best_at(pl_a, ["RW", "LW", "RM", "LM", "RAM", "LAM"])
    fb = _best_at(pl_b, ["RB", "LB", "RWB", "LWB"])
    if winger and fb:
        matchups.append(
            _pair("边路狂飙 · 边锋 vs 边后卫", "Winger vs Fullback", winger, fb)
        )

    # Goalkeeper duel — both sides must have a real keeper.
    gk_a = _best_at(pl_a, ["GK"])
    gk_b = _best_at(pl_b, ["GK"])
    if gk_a and gk_b:
        matchups.append(
            _pair("最后一道防线 · 门将对决", "Last Line · Keeper Duel", gk_a, gk_b)
        )

    # Midfield duel — only when both sides field central mids.
    ma = _best_at(pl_a, ["CM", "CAM", "CDM"])
    mb = _best_at(pl_b, ["CM", "CAM", "CDM"])
    if ma and mb:
        matchups.append(
            _pair("中场争夺战 · 中场 vs 中场", "Midfield Battle", ma, mb)
        )

    logger.info(f"Generated {len(matchups)} key matchups")
    return matchups[:4]
