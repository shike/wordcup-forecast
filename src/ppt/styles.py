"""Visual style for the PPT: dark sports data report aesthetic.

All colors are OKLCH-equivalent RGB hex values picked to render identically
across the python-pptx color stack.
"""
from __future__ import annotations

from pptx.dml.color import RGBColor
from pptx.util import Pt, Emu, Inches


# --- palette ---
BG_DEEP = RGBColor(0x0A, 0x16, 0x28)         # deep space blue
BG_PANEL = RGBColor(0x12, 0x22, 0x3C)         # panel background
BG_CARD = RGBColor(0x1A, 0x2D, 0x4D)          # card background
BG_SOFT = RGBColor(0x22, 0x3A, 0x5F)          # softer panel

GOLD = RGBColor(0xFF, 0xB6, 0x27)             # primary accent (gold)
GOLD_DEEP = RGBColor(0xC8, 0x85, 0x10)        # deeper gold
CYAN = RGBColor(0x00, 0xD4, 0xFF)             # data cyan
RED = RGBColor(0xFF, 0x4D, 0x6D)              # risk / loss
GREEN = RGBColor(0x6E, 0xE0, 0x8E)            # positive / win
GREY = RGBColor(0x9A, 0xB0, 0xC8)             # secondary text
GREY_DARK = RGBColor(0x55, 0x6A, 0x82)        # tertiary text
WHITE = RGBColor(0xF5, 0xF7, 0xFA)            # primary text
LINE = RGBColor(0x2A, 0x3F, 0x60)             # divider lines

# --- fonts (latin) ---
FONT_TITLE = "Inter"
FONT_BODY = "Inter"
FONT_MONO = "JetBrains Mono"

# --- chinese font candidates (PowerPoint will fall back if missing) ---
FONT_CN_TITLE = "Source Han Sans CN"
FONT_CN_BODY = "Source Han Sans CN"


# --- typography ---
TITLE_SIZE = Pt(36)
SUBTITLE_SIZE = Pt(20)
SECTION_SIZE = Pt(24)
BODY_SIZE = Pt(14)
SMALL_SIZE = Pt(11)
BIG_NUMBER_SIZE = Pt(80)
MEDIUM_NUMBER_SIZE = Pt(48)


# --- layout ---
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN = Inches(0.6)
CONTENT_W = SLIDE_W - 2 * MARGIN
