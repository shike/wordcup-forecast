"""Football pitch formation image generation."""
from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont

from src.lineup.formations import get_formation
from src.utils.models import Lineup


# Register a CJK font with matplotlib for Chinese player names
_CJK_FONTS = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "C:\\Windows\\Fonts\\msyh.ttc",
    "C:\\Windows\\Fonts\\msyh.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]
for _p in _CJK_FONTS:
    if os.path.exists(_p):
        try:
            font_manager.fontManager.addfont(_p)
            plt.rcParams["font.sans-serif"] = [font_manager.FontProperties(fname=_p).get_name(), "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            break
        except Exception:
            pass


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a CJK-capable font (covers Latin + Chinese)."""
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "C:\\Windows\\Fonts\\msyh.ttc",
        "C:\\Windows\\Fonts\\msyh.ttf",
        "C:\\Windows\\Fonts\\simhei.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except OSError:
                continue
    return ImageFont.load_default()


def draw_pitch_with_lineup(lineup: Lineup, save_path: Path, kit_color: str = "#FFB627", title: str = "") -> Path:
    """Draw a top-down pitch with player dots at formation coordinates."""
    formation = get_formation(lineup.formation)
    coords = formation.coordinates
    positions = formation.positions

    if len(lineup.players) != 11:
        raise ValueError(f"Expected 11 players, got {len(lineup.players)}")

    fig_w, fig_h = 7.0, 9.0
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor="#0A1628")
    ax.set_facecolor("#0A1628")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.axis("off")

    # Pitch background (vertical, attacking direction up)
    pitch_color = "#1A3A1A"
    line_color = "#F5F7FA"
    ax.add_patch(plt.Rectangle((0.04, 0.02), 0.92, 0.96, facecolor=pitch_color, edgecolor=line_color, linewidth=2.2))
    # halfway line
    ax.plot([0.04, 0.96], [0.50, 0.50], color=line_color, linewidth=1.5)
    # centre circle
    centre = plt.Circle((0.50, 0.50), 0.10, color=line_color, fill=False, linewidth=1.5)
    ax.add_patch(centre)
    # top penalty area
    ax.add_patch(plt.Rectangle((0.20, 0.84), 0.60, 0.14, facecolor="none", edgecolor=line_color, linewidth=1.5))
    ax.add_patch(plt.Rectangle((0.36, 0.92), 0.28, 0.06, facecolor="none", edgecolor=line_color, linewidth=1.2))
    # bottom penalty area
    ax.add_patch(plt.Rectangle((0.20, 0.02), 0.60, 0.14, facecolor="none", edgecolor=line_color, linewidth=1.5))
    ax.add_patch(plt.Rectangle((0.36, 0.02), 0.28, 0.06, facecolor="none", edgecolor=line_color, linewidth=1.2))

    # Stripes
    for i in range(0, 10):
        y0 = 0.02 + i * 0.10
        if i % 2 == 0:
            ax.add_patch(plt.Rectangle((0.04, y0), 0.92, 0.10, facecolor="#15431A", edgecolor="none", alpha=0.6))

    # Draw formation lines connecting players in the same horizontal "line" (#8).
    # Group coordinates by y-band, then connect sorted x's within each band.
    bands: dict[float, list[tuple[float, float]]] = {}
    for (x, y) in coords:
        bands.setdefault(round(y, 2), []).append((x, y))
    for band_pts in bands.values():
        if len(band_pts) >= 2:
            band_pts.sort()
            xs = [p[0] for p in band_pts]
            ys = [p[1] for p in band_pts]
            ax.plot([xs[0], xs[-1]], [ys[0], ys[-1]],
                    color=kit_color, linewidth=1.2, alpha=0.5, zorder=2.5)

    # Player dots
    for (x, y), slot, player in zip(coords, positions, lineup.players):
        # dot
        dot = plt.Circle((x, y), 0.034, facecolor=kit_color, edgecolor="white", linewidth=1.5, zorder=3)
        ax.add_patch(dot)
        # number
        ax.text(x, y, str(player.number or ""), color="#0A1628", ha="center", va="center", fontsize=11, weight="bold", zorder=4)
        # position label above
        ax.text(x, min(y + 0.055, 0.97), slot, color="#9AB0C8", ha="center", va="bottom", fontsize=8, zorder=4)
        # name below (Chinese primary)
        name = player.display_name_cn()
        if len(name) > 6:
            # truncate intelligently (keep first 5 chars)
            name = name[:5] + "…"
        ax.text(x, max(y - 0.055, 0.02), name, color="#F5F7FA", ha="center", va="top", fontsize=9, zorder=4)

    if title:
        ax.set_title(title, color="#F5F7FA", fontsize=14, weight="bold", pad=14)

    fig.tight_layout()
    fig.savefig(save_path, dpi=160, facecolor="#0A1628", bbox_inches="tight")
    plt.close(fig)
    return save_path
