"""Player card image generation: FIFA Ultimate Team style.

Each card has:
- top: position badge + rating
- centre: portrait
- bottom: name + club

If a player has no photo on disk the card is not rendered and the caller
receives an error; the PPT only displays cards for players with real images.
"""
from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.utils.models import Player


# Font loading with CJK + Latin font chain.
# We try multiple CJK-capable fonts on each OS so cards render properly
# wherever the program runs.

_CJK_FONT_CANDIDATES = [
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Windows
    "C:\\Windows\\Fonts\\msyh.ttc",
    "C:\\Windows\\Fonts\\msyh.ttf",
    "C:\\Windows\\Fonts\\simhei.ttf",
    "C:\\Windows\\Fonts\\simsun.ttc",
    # Linux
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # last-resort: latin only
]

_LATIN_FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNSDisplay.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
]


def _load_cjk_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load a CJK-capable font.  Tries OS-specific CJK fonts first."""
    for c in _CJK_FONT_CANDIDATES:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _load_latin_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = _LATIN_FONT_CANDIDATES + _CJK_FONT_CANDIDATES
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Default: try CJK font (covers both Latin + Chinese)."""
    return _load_cjk_font(size, bold)


# Position colour badge
POSITION_COLORS = {
    "GK": "#F4C443",
    "CB": "#3DC1D3",
    "LB": "#3DC1D3",
    "RB": "#3DC1D3",
    "CDM": "#7DCE82",
    "CM": "#7DCE82",
    "CAM": "#7DCE82",
    "LW": "#E63946",
    "RW": "#E63946",
    "ST": "#E63946",
    "CF": "#E63946",
}


def player_has_photo(player: Player) -> bool:
    """Return True if the player has a usable photo on disk."""
    photo_path = player.photo_path
    return bool(photo_path and Path(photo_path).exists())


def render_player_card(player: Player, size: tuple[int, int] = (320, 440), kit_color: str = "#FFB627") -> Path:
    """Render a single player card to a PNG file. Returns the path."""
    img = Image.new("RGB", size, color="#0A1628")
    draw = ImageDraw.Draw(img)

    # Gradient background panels
    panel_color = "#12223C"
    draw.rounded_rectangle((8, 8, size[0] - 8, size[1] - 8), radius=24, fill=panel_color, outline=kit_color, width=3)

    # Position badge top-left
    pos = player.position
    pos_color = POSITION_COLORS.get(pos, "#9AB0C8")
    draw.rounded_rectangle((24, 24, 100, 64), radius=8, fill=pos_color)
    f_pos = _load_font(22, bold=True)
    draw.text((62, 28), pos, fill="#0A1628", font=f_pos, anchor="mm")

    # Rating top-right
    rating = int(round(player.rating))
    draw.rounded_rectangle((size[0] - 96, 24, size[0] - 24, 64), radius=8, fill="#FFB627")
    f_rating = _load_font(30, bold=True)
    draw.text((size[0] - 60, 28), str(rating), fill="#0A1628", font=f_rating, anchor="mm")

    # Portrait area
    portrait_box = (24, 80, size[0] - 24, 280)
    photo_path = player.photo_path
    if not (photo_path and Path(photo_path).exists()):
        raise FileNotFoundError(
            f"无 {player.name} ({player.name_zh}) 的真实头像：photo_path={photo_path}。"
            f"球员卡片只显示有真实照片的球员。"
        )
    photo = Image.open(photo_path).convert("RGBA")
    box_w = portrait_box[2] - portrait_box[0]
    box_h = portrait_box[3] - portrait_box[1]
    photo.thumbnail((box_w, box_h), Image.LANCZOS)
    # circular mask
    mask = Image.new("L", photo.size, 0)
    md = ImageDraw.Draw(mask)
    md.ellipse((0, 0, photo.size[0], photo.size[1]), fill=255)
    photo_layer = Image.new("RGBA", photo.size, (0, 0, 0, 0))
    photo_layer.paste(photo, (0, 0), mask)
    # paste centred in box
    ox = portrait_box[0] + (box_w - photo.size[0]) // 2
    oy = portrait_box[1] + (box_h - photo.size[1]) // 2
    img.paste(photo_layer, (ox, oy), photo_layer)

    # Name (Chinese primary, English as smaller subtitle)
    f_name_cn = _load_font(22, bold=True)
    f_name_en = _load_font(13, bold=False)
    name_cn = player.name_zh or player.name
    if len(name_cn) > 8:
        # split into two lines
        mid = len(name_cn) // 2
        line1 = name_cn[:mid]
        line2 = name_cn[mid:]
        draw.text((size[0] // 2, 300), line1, fill="#F5F7FA", font=f_name_cn, anchor="mm")
        draw.text((size[0] // 2, 326), line2, fill="#F5F7FA", font=f_name_cn, anchor="mm")
    else:
        draw.text((size[0] // 2, 313), name_cn, fill="#F5F7FA", font=f_name_cn, anchor="mm")
    # English name as small subtitle
    if player.name_zh and player.name_zh != player.name:
        draw.text((size[0] // 2, 348), player.name, fill="#9AB0C8", font=f_name_en, anchor="mm")

    # Stats grid
    f_stat_label = _load_font(11, bold=False)
    f_stat_value = _load_font(15, bold=True)
    stats = [
        ("速度", player.rating + 0.3),
        ("射门", player.rating + 0.1),
        ("传球", player.rating - 0.1),
        ("盘带", player.rating + 0.2),
        ("防守", player.rating - 0.4 if pos not in ["GK", "CB", "LB", "RB"] else player.rating + 0.3),
        ("身体", player.rating - 0.2),
    ]
    for i, (label, val) in enumerate(stats):
        col = i % 3
        row = i // 3
        sx = 32 + col * 90
        sy = 360 + row * 36
        draw.text((sx, sy), label, fill="#9AB0C8", font=f_stat_label)
        draw.text((sx + 50, sy - 2), str(int(round(val))), fill="#F5F7FA", font=f_stat_value, anchor="mm")

    # Footer: club + number
    f_foot = _load_font(10, bold=False)
    foot = f"#{player.number}  ·  {player.club or '—'}"
    draw.text((size[0] // 2, size[1] - 20), foot, fill="#9AB0C8", font=f_foot, anchor="mm")

    out = Path(f"/tmp/球员卡_{player.id}.png")
    img.save(out, "PNG")
    return out
