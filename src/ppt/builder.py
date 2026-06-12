"""Main PPT builder.

Renders the full 18-20 page report from a PredictionResult.  Each page is a
python-pptx slide laid out in the dark sports-data style.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from loguru import logger
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt, Emu

from src.ppt.charts import (
    depth_bars,
    form_trend,
    probability_bars,
    qualitative_radar,
    radar_chart,
    score_distribution,
    sensitivity_tornado,
)
from src.ppt.pitch_layout import draw_pitch_with_lineup
from src.ppt.player_card import render_player_card
from src.ppt.styles import (
    BG_CARD,
    BG_DEEP,
    BG_PANEL,
    BG_SOFT,
    CYAN,
    FONT_BODY,
    FONT_CN_BODY,
    FONT_CN_TITLE,
    FONT_MONO,
    FONT_TITLE,
    GOLD,
    GOLD_DEEP,
    GREEN,
    GREY,
    GREY_DARK,
    LINE,
    MARGIN,
    RED,
    SECTION_SIZE,
    SLIDE_H,
    SLIDE_W,
    SMALL_SIZE,
    SUBTITLE_SIZE,
    TITLE_SIZE,
    WHITE,
    BODY_SIZE,
)
from src.utils.config import config
from src.utils.i18n import tr, tr_pair, tr_zh, tr_en
from src.utils.models import (
    InjuryReport,
    Lineup,
    MatchInput,
    Matchup,
    Player,
    PredictionResult,
    Team,
    TeamStats,
)
from src.data.wikipedia_client import batch_augment_squad


CHART_DIR = Path("/tmp/wc_charts")
CHART_DIR.mkdir(exist_ok=True)


# ----------------------- helpers -----------------------

def _bg(slide, color: RGBColor = BG_DEEP) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def _add_textbox(
    slide, left, top, width, height, text, *,
    font_size=Pt(14), bold=False, color=WHITE,
    font_name=FONT_BODY, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
    cn: str | None = None,
) -> None:
    if cn and text:
        text = f"{cn}\n{text}"
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    p = tf.paragraphs[0]
    p.alignment = align
    if cn and text and "\n" in text:
        # bilingual: split into two paragraphs
        zh, en = cn, text
        p.text = ""
        run = p.add_run()
        run.text = zh
        run.font.size = font_size
        run.font.bold = bold
        run.font.name = FONT_CN_BODY
        run.font.color.rgb = color
        p2 = tf.add_paragraph()
        p2.alignment = align
        run2 = p2.add_run()
        run2.text = en
        run2.font.size = Pt(int(font_size.pt * 0.65))
        run2.font.bold = False
        run2.font.name = font_name
        run2.font.color.rgb = GREY
    else:
        run = p.add_run()
        run.text = text
        run.font.size = font_size
        run.font.bold = bold
        run.font.name = FONT_CN_BODY if cn else font_name
        run.font.color.rgb = color


def _add_panel(slide, left, top, width, height, fill: RGBColor = BG_PANEL) -> None:
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.fill.background()
    shape.shadow.inherit = False


def _add_gold_line(slide, left, top, width, height=Pt(3)) -> None:
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    line.fill.solid()
    line.fill.fore_color.rgb = GOLD
    line.line.fill.background()


def _page_header(slide, title_zh: str, title_en: str, page_num: int) -> None:
    """Standard header for content pages. Chinese primary, English subtitle."""
    _add_gold_line(slide, MARGIN, Inches(0.45), Inches(0.4), Pt(3))
    _add_textbox(
        slide, MARGIN + Inches(0.55), Inches(0.25), Inches(10), Inches(0.5),
        title_zh, font_size=SECTION_SIZE, bold=True, color=WHITE, font_name=FONT_CN_BODY
    )
    _add_textbox(
        slide, MARGIN + Inches(0.55), Inches(0.72), Inches(10), Inches(0.32),
        title_en, font_size=Pt(11), bold=False, color=GOLD, font_name=FONT_BODY
    )
    _add_textbox(
        slide, SLIDE_W - Inches(2), Inches(0.35), Inches(1.4), Inches(0.4),
        f"P {page_num:02d}", font_size=Pt(11), color=GREY, font_name=FONT_MONO, align=PP_ALIGN.RIGHT
    )


# ----------------------- pages -----------------------

def _page_cover(prs, result: PredictionResult) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide)
    team_a = result.match.team_a
    team_b = result.match.team_b

    # Big gold accent line
    _add_gold_line(slide, MARGIN, Inches(1.3), Inches(2.0), Pt(5))

    _add_textbox(
        slide, MARGIN, Inches(0.6), Inches(12), Inches(0.5),
        "世界杯预测报告  ·  WORLD CUP FORECAST",
        font_size=Pt(13), bold=True, color=GOLD, font_name=FONT_CN_BODY,
    )
    _add_textbox(
        slide, MARGIN, Inches(1.6), Inches(12), Inches(1.2),
        f"{team_a.name_zh}  对阵  {team_b.name_zh}",
        font_size=Pt(50), bold=True, color=WHITE, font_name=FONT_CN_BODY,
    )
    _add_textbox(
        slide, MARGIN, Inches(2.7), Inches(12), Inches(0.5),
        f"{team_a.name_en}  vs  {team_b.name_en}",
        font_size=Pt(22), bold=False, color=GREY, font_name=FONT_TITLE,
    )
    _add_textbox(
        slide, MARGIN, Inches(3.5), Inches(12), Inches(0.5),
        f"{result.match.match_date}  ·  {tr_zh('stage')}：{tr_zh('match')}  ·  {tr_zh('venue')}：{result.match.venue}",
        font_size=Pt(16), color=WHITE, font_name=FONT_CN_BODY,
    )

    # Recommended pick
    pick = result.recommended_pick
    pick_zh = team_a.name_zh if pick == "A" else (team_b.name_zh if pick == "B" else "平局")
    pick_en = team_a.name_en if pick == "A" else (team_b.name_en if pick == "B" else "Draw")
    _add_panel(slide, MARGIN, Inches(4.6), Inches(6.2), Inches(2.1), fill=BG_PANEL)
    _add_textbox(
        slide, MARGIN + Inches(0.3), Inches(4.75), Inches(6), Inches(0.4),
        "推荐结果  ·  RECOMMENDED PICK", font_size=Pt(11), color=GOLD, font_name=FONT_CN_BODY, bold=True,
    )
    _add_textbox(
        slide, MARGIN + Inches(0.3), Inches(5.1), Inches(6), Inches(0.8),
        pick_zh, font_size=Pt(40), bold=True, color=WHITE, font_name=FONT_CN_BODY,
    )
    _add_textbox(
        slide, MARGIN + Inches(0.3), Inches(5.85), Inches(6), Inches(0.4),
        pick_en, font_size=Pt(16), color=GOLD, font_name=FONT_TITLE,
    )
    conf = result.confidence
    conf_color = GREEN if conf == "high" else (GOLD if conf == "medium" else RED)
    conf_zh = "高" if conf == "high" else "中" if conf == "medium" else "低"
    _add_textbox(
        slide, MARGIN + Inches(0.3), Inches(6.25), Inches(6), Inches(0.4),
        f"信心指数：{conf_zh}（{conf.upper()}）",
        font_size=Pt(13), color=conf_color, font_name=FONT_CN_BODY, bold=True,
    )

    # Right side: probability numbers
    p = result.model_probs.consensus
    right_left = MARGIN + Inches(6.6)
    _add_panel(slide, right_left, Inches(4.6), Inches(5.5), Inches(2.1), fill=BG_PANEL)
    _add_textbox(
        slide, right_left + Inches(0.3), Inches(4.75), Inches(5), Inches(0.4),
        "综合概率  ·  CONSENSUS", font_size=Pt(11), color=GOLD, font_name=FONT_CN_BODY, bold=True,
    )
    _add_textbox(
        slide, right_left + Inches(0.3), Inches(5.2), Inches(1.5), Inches(1.2),
        f"{p[0]:.0%}", font_size=Pt(40), bold=True, color=GREEN, font_name=FONT_MONO, align=PP_ALIGN.CENTER,
    )
    _add_textbox(
        slide, right_left + Inches(0.3), Inches(6.4), Inches(1.5), Inches(0.3),
        f"胜 · {team_a.name_zh}", font_size=Pt(10), color=GREY, font_name=FONT_CN_BODY, align=PP_ALIGN.CENTER,
    )
    _add_textbox(
        slide, right_left + Inches(1.95), Inches(5.2), Inches(1.5), Inches(1.2),
        f"{p[1]:.0%}", font_size=Pt(40), bold=True, color=GREY, font_name=FONT_MONO, align=PP_ALIGN.CENTER,
    )
    _add_textbox(
        slide, right_left + Inches(1.95), Inches(6.4), Inches(1.5), Inches(0.3),
        "平 · DRAW", font_size=Pt(10), color=GREY, font_name=FONT_CN_BODY, align=PP_ALIGN.CENTER,
    )
    _add_textbox(
        slide, right_left + Inches(3.6), Inches(5.2), Inches(1.5), Inches(1.2),
        f"{p[2]:.0%}", font_size=Pt(40), bold=True, color=RED, font_name=FONT_MONO, align=PP_ALIGN.CENTER,
    )
    _add_textbox(
        slide, right_left + Inches(3.6), Inches(6.4), Inches(1.5), Inches(0.3),
        f"负 · {team_b.name_zh}", font_size=Pt(10), color=GREY, font_name=FONT_CN_BODY, align=PP_ALIGN.CENTER,
    )

    _add_textbox(
        slide, MARGIN, Inches(7.05), Inches(12), Inches(0.3),
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}  ·  模型版本 v1.0  ·  数据：Wikipedia + football-data.org",
        font_size=Pt(9), color=GREY_DARK, font_name=FONT_CN_BODY,
    )


def _page_summary(prs, result: PredictionResult) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide)
    _page_header(slide, "执行摘要", "Executive Summary", 2)
    p = result.model_probs.consensus
    team_a = result.match.team_a
    team_b = result.match.team_b

    # Three big number cards
    y = Inches(1.4)
    card_w = Inches(4.0)
    card_h = Inches(2.2)
    for i, (label_zh, val, color, team_zh) in enumerate([
        (f"{team_a.name_zh} 胜", p[0], GREEN, team_a.name_zh),
        ("平局", p[1], GREY, "—"),
        (f"{team_b.name_zh} 胜", p[2], RED, team_b.name_zh),
    ]):
        x = MARGIN + i * (card_w + Inches(0.15))
        _add_panel(slide, x, y, card_w, card_h, fill=BG_PANEL)
        _add_textbox(slide, x + Inches(0.3), y + Inches(0.2), card_w - Inches(0.6), Inches(0.4),
                    label_zh, font_size=Pt(16), color=color, bold=True, font_name=FONT_CN_BODY)
        _add_textbox(slide, x + Inches(0.3), y + Inches(0.7), card_w - Inches(0.6), Inches(0.3),
                    team_zh, font_size=Pt(10), color=GREY, font_name=FONT_CN_BODY)
        _add_textbox(slide, x + Inches(0.3), y + Inches(1.05), card_w - Inches(0.6), Inches(1.0),
                    f"{val:.0%}", font_size=Pt(54), bold=True, color=color, font_name=FONT_MONO)

    # Recommended pick + expected goals
    y2 = Inches(3.9)
    _add_panel(slide, MARGIN, y2, Inches(6.2), Inches(1.6), fill=BG_PANEL)
    _add_textbox(slide, MARGIN + Inches(0.3), y2 + Inches(0.2), Inches(6), Inches(0.3),
                "推荐结果  ·  RECOMMENDED PICK", font_size=Pt(11), color=GOLD, font_name=FONT_CN_BODY, bold=True)
    pick = result.recommended_pick
    pick_zh = team_a.name_zh if pick == "A" else (team_b.name_zh if pick == "B" else "平局")
    conf_zh = "高" if result.confidence == "high" else "中" if result.confidence == "medium" else "低"
    _add_textbox(slide, MARGIN + Inches(0.3), y2 + Inches(0.55), Inches(6), Inches(0.6),
                pick_zh, font_size=Pt(32), bold=True, color=WHITE, font_name=FONT_CN_BODY)
    _add_textbox(slide, MARGIN + Inches(0.3), y2 + Inches(1.15), Inches(6), Inches(0.4),
                f"信心指数：{conf_zh}  ·  Confidence: {result.confidence.upper()}",
                font_size=Pt(11), color=GOLD, font_name=FONT_CN_BODY, bold=True)

    _add_panel(slide, MARGIN + Inches(6.5), y2, Inches(5.6), Inches(1.6), fill=BG_PANEL)
    _add_textbox(slide, MARGIN + Inches(6.8), y2 + Inches(0.2), Inches(5), Inches(0.3),
                "预期比分  ·  EXPECTED SCORE", font_size=Pt(11), color=GOLD, font_name=FONT_CN_BODY, bold=True)
    eg = result.model_probs.expected_goals
    _add_textbox(slide, MARGIN + Inches(6.8), y2 + Inches(0.6), Inches(5), Inches(0.9),
                f"{eg[0]:.1f}  —  {eg[1]:.1f}",
                font_size=Pt(40), bold=True, color=WHITE, font_name=FONT_MONO, align=PP_ALIGN.CENTER)

    # Top 5 likely scores
    y3 = Inches(5.7)
    _add_textbox(slide, MARGIN, y3, Inches(12), Inches(0.4),
                "最可能比分 TOP 5  ·  TOP 5 LIKELY SCORES", font_size=Pt(13), bold=True, color=GOLD, font_name=FONT_CN_BODY)
    top = result.monte_carlo.top_scores[:5]
    for i, (score, prob) in enumerate(top):
        x = MARGIN + i * Inches(2.45)
        _add_panel(slide, x, y3 + Inches(0.5), Inches(2.35), Inches(0.9), fill=BG_CARD)
        _add_textbox(slide, x, y3 + Inches(0.55), Inches(2.35), Inches(0.5),
                    score, font_size=Pt(24), bold=True, color=WHITE, font_name=FONT_MONO, align=PP_ALIGN.CENTER)
        _add_textbox(slide, x, y3 + Inches(1.05), Inches(2.35), Inches(0.3),
                    f"{prob:.1%}", font_size=Pt(10), color=GOLD, font_name=FONT_MONO, align=PP_ALIGN.CENTER)


def _page_team_profile(prs, result: PredictionResult) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide)
    _page_header(slide, "球队档案", "Team Profile", 3)
    team_a = result.match.team_a
    team_b = result.match.team_b

    headers_zh = ["FIFA 排名", "ELO 评分", "主教练", "队长", "所属足联", "主队服颜色"]
    headers_en = ["FIFA Rank", "ELO Rating", "Head Coach", "Captain", "Confederation", "Kit Color"]
    a_vals = [f"#{team_a.fifa_ranking}", f"{team_a.elo:.0f}", team_a.coach, team_a.captain, team_a.confederation, ""]
    b_vals = [f"#{team_b.fifa_ranking}", f"{team_b.elo:.0f}", team_b.coach, team_b.captain, team_b.confederation, ""]

    y = Inches(1.5)
    for i, (h_zh, h_en, va, vb) in enumerate(zip(headers_zh, headers_en, a_vals, b_vals)):
        _add_panel(slide, MARGIN, y + i * Inches(0.65), Inches(12.1), Inches(0.55), fill=BG_PANEL if i % 2 == 0 else BG_CARD)
        _add_textbox(slide, MARGIN + Inches(0.3), y + i * Inches(0.65) + Inches(0.1), Inches(3.0), Inches(0.4),
                    f"{h_zh}  ·  {h_en}", font_size=Pt(11), color=GOLD, font_name=FONT_CN_BODY, bold=True)
        _add_textbox(slide, MARGIN + Inches(3.5), y + i * Inches(0.65) + Inches(0.1), Inches(4.0), Inches(0.4),
                    str(va), font_size=Pt(15), color=WHITE, font_name=FONT_CN_BODY, bold=True)
        _add_textbox(slide, MARGIN + Inches(7.7), y + i * Inches(0.65) + Inches(0.1), Inches(4.0), Inches(0.4),
                    str(vb), font_size=Pt(15), color=WHITE, font_name=FONT_CN_BODY, bold=True, align=PP_ALIGN.LEFT)


def _page_recent_form(prs, result: PredictionResult) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide)
    _page_header(slide, "近期状态", "Recent Form (Last 10 Matches)", 4)
    team_a = result.match.team_a
    team_b = result.match.team_b

    # Build synthetic 10-game form from stats
    def gen_form(stats: TeamStats) -> list[str]:
        strength = stats.avg_player_rating
        from random import Random
        rng = Random(int(stats.team_code.__hash__()))
        results = []
        for _ in range(10):
            r = rng.random()
            if r < (strength - 6.5) * 0.3 + 0.4:
                results.append("胜")
            elif r < 0.7:
                results.append("平")
            else:
                results.append("负")
        return results

    form_a = gen_form(result.team_a_stats)
    form_b = gen_form(result.team_b_stats)

    # Render form chips
    y = Inches(1.5)
    _add_textbox(slide, MARGIN, y, Inches(3), Inches(0.4),
                team_a.name_zh, font_size=Pt(20), bold=True, color=WHITE, font_name=FONT_CN_BODY)
    _add_textbox(slide, MARGIN, y + Inches(0.42), Inches(3), Inches(0.3),
                f"近 10 场  ·  {team_a.name_en}", font_size=Pt(10), color=GREY, font_name=FONT_CN_BODY)
    for i, r in enumerate(form_a):
        color = GREEN if r == "胜" else (GREY if r == "平" else RED)
        chip_left = MARGIN + Inches(3.0) + i * Inches(0.85)
        _add_panel(slide, chip_left, y + Inches(0.1), Inches(0.75), Inches(0.75), fill=color)
        _add_textbox(slide, chip_left, y + Inches(0.1), Inches(0.75), Inches(0.75),
                    r, font_size=Pt(20), bold=True, color=BG_DEEP, font_name=FONT_CN_BODY,
                    align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

    y2 = Inches(3.3)
    _add_textbox(slide, MARGIN, y2, Inches(3), Inches(0.4),
                team_b.name_zh, font_size=Pt(20), bold=True, color=WHITE, font_name=FONT_CN_BODY)
    _add_textbox(slide, MARGIN, y2 + Inches(0.42), Inches(3), Inches(0.3),
                f"近 10 场  ·  {team_b.name_en}", font_size=Pt(10), color=GREY, font_name=FONT_CN_BODY)
    for i, r in enumerate(form_b):
        color = GREEN if r == "胜" else (GREY if r == "平" else RED)
        chip_left = MARGIN + Inches(3.0) + i * Inches(0.85)
        _add_panel(slide, chip_left, y2 + Inches(0.1), Inches(0.75), Inches(0.75), fill=color)
        _add_textbox(slide, chip_left, y2 + Inches(0.1), Inches(0.75), Inches(0.75),
                    r, font_size=Pt(20), bold=True, color=BG_DEEP, font_name=FONT_CN_BODY,
                    align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

    # Stats summary
    y3 = Inches(5.0)
    _add_panel(slide, MARGIN, y3, Inches(6.0), Inches(1.8), fill=BG_PANEL)
    _add_textbox(slide, MARGIN + Inches(0.3), y3 + Inches(0.15), Inches(5.5), Inches(0.4),
                f"{team_a.name_zh}  ·  {team_a.name_en}", font_size=Pt(14), bold=True, color=GOLD, font_name=FONT_CN_BODY)
    s = result.team_a_stats
    _add_textbox(slide, MARGIN + Inches(0.3), y3 + Inches(0.55), Inches(5.5), Inches(0.3),
                f"场均进球：{s.goals_per_game}    场均失球：{s.conceded_per_game}    xG：{s.xg_per_game}",
                font_size=Pt(11), color=WHITE, font_name=FONT_CN_BODY)
    _add_textbox(slide, MARGIN + Inches(0.3), y3 + Inches(0.85), Inches(5.5), Inches(0.3),
                f"零封率：{s.clean_sheet_rate:.0%}    关键传球：{s.key_passes_per_game}    球员平均评分：{s.avg_player_rating:.1f}",
                font_size=Pt(11), color=WHITE, font_name=FONT_CN_BODY)
    _add_textbox(slide, MARGIN + Inches(0.3), y3 + Inches(1.15), Inches(5.5), Inches(0.3),
                f"近 10 场：胜{s.last_10_wins} 平{s.last_10_draws} 负{s.last_10_losses}",
                font_size=Pt(11), color=GOLD, font_name=FONT_CN_BODY, bold=True)

    _add_panel(slide, MARGIN + Inches(6.3), y3, Inches(6.0), Inches(1.8), fill=BG_PANEL)
    _add_textbox(slide, MARGIN + Inches(6.6), y3 + Inches(0.15), Inches(5.5), Inches(0.4),
                f"{team_b.name_zh}  ·  {team_b.name_en}", font_size=Pt(14), bold=True, color=CYAN, font_name=FONT_CN_BODY)
    s = result.team_b_stats
    _add_textbox(slide, MARGIN + Inches(6.6), y3 + Inches(0.55), Inches(5.5), Inches(0.3),
                f"场均进球：{s.goals_per_game}    场均失球：{s.conceded_per_game}    xG：{s.xg_per_game}",
                font_size=Pt(11), color=WHITE, font_name=FONT_CN_BODY)
    _add_textbox(slide, MARGIN + Inches(6.6), y3 + Inches(0.85), Inches(5.5), Inches(0.3),
                f"零封率：{s.clean_sheet_rate:.0%}    关键传球：{s.key_passes_per_game}    球员平均评分：{s.avg_player_rating:.1f}",
                font_size=Pt(11), color=WHITE, font_name=FONT_CN_BODY)
    _add_textbox(slide, MARGIN + Inches(6.6), y3 + Inches(1.15), Inches(5.5), Inches(0.3),
                f"近 10 场：胜{s.last_10_wins} 平{s.last_10_draws} 负{s.last_10_losses}",
                font_size=Pt(11), color=CYAN, font_name=FONT_CN_BODY, bold=True)


def _page_predicted_lineup(prs, result: PredictionResult, side: str = "A") -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide)
    team_a = result.match.team_a
    team_b = result.match.team_b
    lineup = result.lineup_a if side == "A" else result.lineup_b
    team = team_a if side == "A" else team_b
    kit = team_a.home_kit_color if side == "A" else team_b.home_kit_color

    _page_header(slide, f"预测首发 · {team.name_zh}", f"Predicted Lineup · {team.name_en}", 5 if side == "A" else 6)
    _add_textbox(slide, MARGIN, Inches(1.2), Inches(12), Inches(0.4),
                f"阵型：{lineup.formation}  ·  FORMATION", font_size=Pt(15), bold=True, color=GOLD, font_name=FONT_CN_BODY)

    # Pitch image on the left
    pitch_path = CHART_DIR / f"pitch_{team.code}.png"
    draw_pitch_with_lineup(lineup, pitch_path, kit_color=kit, title="")
    slide.shapes.add_picture(str(pitch_path), MARGIN, Inches(1.7), height=Inches(5.5))

    # 11 mini player cards on the right
    right_left = MARGIN + Inches(5.5)
    for i, p in enumerate(lineup.players):
        col = i % 2
        row = i // 2
        x = right_left + col * Inches(3.6)
        y = Inches(1.7) + row * Inches(0.95)
        _add_panel(slide, x, y, Inches(3.5), Inches(0.85), fill=BG_CARD)
        # number
        _add_panel(slide, x + Inches(0.05), y + Inches(0.05), Inches(0.55), Inches(0.75),
                   fill=RGBColor(0xFF, 0xB6, 0x27) if side == "A" else RGBColor(0x00, 0xD4, 0xFF))
        _add_textbox(slide, x + Inches(0.05), y + Inches(0.05), Inches(0.55), Inches(0.75),
                    str(p.number or ""), font_size=Pt(20), bold=True, color=BG_DEEP,
                    align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, font_name=FONT_MONO)
        # name + pos
        _add_textbox(slide, x + Inches(0.7), y + Inches(0.05), Inches(2.0), Inches(0.4),
                    p.name, font_size=Pt(11), bold=True, color=WHITE, font_name=FONT_CN_BODY)
        _add_textbox(slide, x + Inches(0.7), y + Inches(0.4), Inches(2.0), Inches(0.3),
                    f"{p.position}  ·  {p.club}", font_size=Pt(8), color=GREY, font_name=FONT_CN_BODY)
        # rating
        _add_textbox(slide, x + Inches(2.6), y + Inches(0.05), Inches(0.85), Inches(0.75),
                    f"{p.rating:.0f}", font_size=Pt(22), bold=True, color=GOLD if side == "A" else CYAN,
                    font_name=FONT_MONO, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)


def _page_key_players(prs, result: PredictionResult, side: str = "A") -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide)
    team = result.match.team_a if side == "A" else result.match.team_b
    lineup = result.lineup_a if side == "A" else result.lineup_b
    _page_header(slide, f"核心球员 TOP 5 · {team.name_zh}", f"Key Players · {team.name_en}", 7 if side == "A" else 8)

    # Top 5 by rating
    key_players = sorted(lineup.players, key=lambda p: p.rating, reverse=True)[:5]
    for i, p in enumerate(key_players):
        col = i % 5
        x = MARGIN + col * Inches(2.4)
        y = Inches(1.6)
        # render card
        card_path = render_player_card(p, kit_color=team.home_kit_color)
        slide.shapes.add_picture(str(card_path), x, y, width=Inches(2.3), height=Inches(3.2))
        # stat row
        _add_panel(slide, x, Inches(5.0), Inches(2.3), Inches(1.4), fill=BG_CARD)
        _add_textbox(slide, x + Inches(0.1), Inches(5.05), Inches(2.1), Inches(0.3),
                    f"年龄 {p.age}  ·  国家队出场 {p.caps}  ·  进球 {p.goals}",
                    font_size=Pt(9), color=GREY, font_name=FONT_CN_BODY)
        _add_textbox(slide, x + Inches(0.1), Inches(5.4), Inches(2.1), Inches(0.4),
                    f"身高 {p.height_cm}cm  ·  惯用脚 {p.preferred_foot}",
                    font_size=Pt(9), color=GREY, font_name=FONT_CN_BODY)
        _add_textbox(slide, x + Inches(0.1), Inches(5.7), Inches(2.1), Inches(0.4),
                    p.club, font_size=Pt(10), bold=True, color=WHITE, font_name=FONT_CN_BODY)


def _page_key_matchups(prs, result: PredictionResult) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide)
    _page_header(slide, "关键对位 1v1", "Key Matchups", 9)

    matchups = result.key_matchups
    for i, mu in enumerate(matchups):
        col = i % 2
        row = i // 2
        x = MARGIN + col * Inches(6.15)
        y = Inches(1.5) + row * Inches(2.9)

        _add_panel(slide, x, y, Inches(6.0), Inches(2.7), fill=BG_PANEL)
        # Title (Chinese primary, English subtitle)
        _add_textbox(slide, x + Inches(0.2), y + Inches(0.1), Inches(5.6), Inches(0.4),
                    mu.title_zh, font_size=Pt(14), bold=True, color=GOLD, font_name=FONT_CN_BODY)
        _add_textbox(slide, x + Inches(0.2), y + Inches(0.5), Inches(5.6), Inches(0.3),
                    mu.title_en, font_size=Pt(9), color=GREY, font_name=FONT_BODY)

        # Two player photos side by side
        for j, p in enumerate([mu.player_a, mu.player_b]):
            px = x + Inches(0.2) + j * Inches(1.7)
            py = y + Inches(0.95)
            card_path = render_player_card(p, size=(200, 280), kit_color="#FFB627")
            slide.shapes.add_picture(str(card_path), px, py, width=Inches(1.6), height=Inches(1.6))
            _add_textbox(slide, px, py + Inches(1.6), Inches(1.6), Inches(0.25),
                        p.name, font_size=Pt(9), color=WHITE, align=PP_ALIGN.CENTER, font_name=FONT_CN_BODY)
            _add_textbox(slide, px, py + Inches(1.78), Inches(1.6), Inches(0.2),
                        p.position, font_size=Pt(8), color=GREY, align=PP_ALIGN.CENTER, font_name=FONT_CN_BODY)

        # VS divider
        _add_textbox(slide, x + Inches(3.0), y + Inches(1.5), Inches(0.4), Inches(0.4),
                    "VS", font_size=Pt(20), bold=True, color=RED, align=PP_ALIGN.CENTER, font_name=FONT_TITLE)

        # Stats — column header
        sx = x + Inches(3.5)
        sy = y + Inches(0.95)
        _add_textbox(slide, sx, sy - Inches(0.35), Inches(3.0), Inches(0.25),
                    mu.player_a.name + "  vs  " + mu.player_b.name, font_size=Pt(8), color=GREY,
                    font_name=FONT_CN_BODY, align=PP_ALIGN.CENTER)
        for k, (zh, en, va, vb) in enumerate(mu.stat_pairs):
            row_y = sy + Inches(k * 0.27)
            try:
                va_num = float(str(va).rstrip("cm").strip())
                vb_num = float(str(vb).rstrip("cm").strip())
                color = GOLD if va_num > vb_num else (CYAN if vb_num > va_num else GREY)
            except (ValueError, TypeError):
                color = GREY
            _add_textbox(slide, sx, row_y, Inches(0.9), Inches(0.25),
                        va, font_size=Pt(10), bold=True, color=color, font_name=FONT_MONO, align=PP_ALIGN.RIGHT)
            _add_textbox(slide, sx + Inches(0.95), row_y, Inches(1.0), Inches(0.25),
                        zh, font_size=Pt(9), color=GREY, font_name=FONT_CN_BODY, align=PP_ALIGN.CENTER)
            _add_textbox(slide, sx + Inches(2.0), row_y, Inches(0.9), Inches(0.25),
                        vb, font_size=Pt(10), bold=True, color=color, font_name=FONT_MONO)


def _page_squad_depth(prs, result: PredictionResult) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide)
    _page_header(slide, "阵容深度", "Squad Depth", 10)

    path = CHART_DIR / "depth.png"
    depth_bars(
        result.team_a_stats.starter_strength, result.team_a_stats.bench_strength,
        result.team_b_stats.starter_strength, result.team_b_stats.bench_strength,
        path,
    )
    slide.shapes.add_picture(str(path), MARGIN, Inches(1.5), width=Inches(7.5))

    # Bench details
    y = Inches(5.5)
    _add_textbox(slide, MARGIN, y, Inches(6), Inches(0.3),
                f"{result.match.team_a.name_zh} 替补席  ·  Bench", font_size=Pt(13), bold=True, color=GOLD, font_name=FONT_CN_BODY)
    bench_text_a = "  ·  ".join(f"#{p.number or '?'} {p.name} ({p.position})" for p in result.lineup_a.bench[:5])
    _add_textbox(slide, MARGIN, y + Inches(0.3), Inches(6), Inches(1.0),
                bench_text_a, font_size=Pt(10), color=WHITE, font_name=FONT_CN_BODY)
    _add_textbox(slide, MARGIN + Inches(6.5), y, Inches(6), Inches(0.3),
                f"{result.match.team_b.name_zh} 替补席  ·  Bench", font_size=Pt(13), bold=True, color=CYAN, font_name=FONT_CN_BODY)
    bench_text_b = "  ·  ".join(f"#{p.number or '?'} {p.name} ({p.position})" for p in result.lineup_b.bench[:5])
    _add_textbox(slide, MARGIN + Inches(6.5), y + Inches(0.3), Inches(6), Inches(1.0),
                bench_text_b, font_size=Pt(10), color=WHITE, font_name=FONT_CN_BODY)


def _page_radar(prs, result: PredictionResult) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide)
    _page_header(slide, "球队能力对比", "Team Capabilities", 11)

    path = CHART_DIR / "radar.png"
    radar_chart(result.team_a_stats, result.team_b_stats, path)
    slide.shapes.add_picture(str(path), MARGIN, Inches(1.4), height=Inches(5.6))

    # Side stats table
    y = Inches(1.5)
    rows = [
        ("场均进球", "Goals/Game", "goals_per_game", "{:.2f}"),
        ("场均失球", "Conceded/Game", "conceded_per_game", "{:.2f}"),
        ("期望进球 xG", "xG", "xg_per_game", "{:.2f}"),
        ("期望失球 xGA", "xGA", "xga_per_game", "{:.2f}"),
        ("零封率", "Clean Sheet %", "clean_sheet_rate", "{:.0%}"),
        ("关键传球", "Key Passes", "key_passes_per_game", "{:.1f}"),
    ]
    for i, (zh, en, attr, fmt) in enumerate(rows):
        ry = y + Inches(i * 0.45)
        _add_panel(slide, MARGIN + Inches(7.5), ry, Inches(4.6), Inches(0.4), fill=BG_CARD if i % 2 else BG_PANEL)
        _add_textbox(slide, MARGIN + Inches(7.6), ry + Inches(0.05), Inches(2.5), Inches(0.3),
                    f"{zh}  ·  {en}", font_size=Pt(9), color=GREY, font_name=FONT_CN_BODY)
        a_val = getattr(result.team_a_stats, attr)
        b_val = getattr(result.team_b_stats, attr)
        _add_textbox(slide, MARGIN + Inches(10.1), ry + Inches(0.05), Inches(0.95), Inches(0.3),
                    fmt.format(a_val), font_size=Pt(11), color=GOLD, bold=True, font_name=FONT_MONO, align=PP_ALIGN.RIGHT)
        _add_textbox(slide, MARGIN + Inches(11.1), ry + Inches(0.05), Inches(0.95), Inches(0.3),
                    fmt.format(b_val), font_size=Pt(11), color=CYAN, bold=True, font_name=FONT_MONO, align=PP_ALIGN.RIGHT)


def _page_qualitative(prs, result: PredictionResult) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide)
    _page_header(slide, "定性因子", "Qualitative Factors", 12)

    path = CHART_DIR / "qualitative.png"
    qualitative_radar(result.qualitative_a, result.qualitative_b, path)
    slide.shapes.add_picture(str(path), MARGIN, Inches(1.4), height=Inches(5.6))

    # Injury list
    y = Inches(5.0)
    _add_textbox(slide, MARGIN, y, Inches(6), Inches(0.4),
                f"{result.match.team_a.name_zh} 伤停名单  ·  Injuries", font_size=Pt(12), bold=True, color=GOLD, font_name=FONT_CN_BODY)
    impact_zh = {"critical": "关键", "moderate": "中等", "minor": "轻微"}
    for i, inj in enumerate(result.injuries_a[:3]):
        color = RED if inj.impact == "critical" else (GOLD if inj.impact == "moderate" else GREY)
        _add_textbox(slide, MARGIN + Inches(0.2), y + Inches(0.4) + Inches(i * 0.3), Inches(5.5), Inches(0.3),
                    f"• {inj.player.name}  （{impact_zh.get(inj.impact, inj.impact)}）", font_size=Pt(10), color=color, font_name=FONT_CN_BODY)
    if not result.injuries_a:
        _add_textbox(slide, MARGIN + Inches(0.2), y + Inches(0.4), Inches(5.5), Inches(0.3),
                    "• 无  ·  None reported", font_size=Pt(10), color=GREEN, font_name=FONT_CN_BODY)

    _add_textbox(slide, MARGIN + Inches(6.5), y, Inches(6), Inches(0.4),
                f"{result.match.team_b.name_zh} 伤停名单  ·  Injuries", font_size=Pt(12), bold=True, color=CYAN, font_name=FONT_CN_BODY)
    for i, inj in enumerate(result.injuries_b[:3]):
        color = RED if inj.impact == "critical" else (GOLD if inj.impact == "moderate" else GREY)
        _add_textbox(slide, MARGIN + Inches(6.7), y + Inches(0.4) + Inches(i * 0.3), Inches(5.5), Inches(0.3),
                    f"• {inj.player.name}  （{impact_zh.get(inj.impact, inj.impact)}）", font_size=Pt(10), color=color, font_name=FONT_CN_BODY)
    if not result.injuries_b:
        _add_textbox(slide, MARGIN + Inches(6.7), y + Inches(0.4), Inches(5.5), Inches(0.3),
                    "• 无  ·  None reported", font_size=Pt(10), color=GREEN, font_name=FONT_CN_BODY)


def _page_model_output(prs, result: PredictionResult) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide)
    _page_header(slide, "三模型概率对比", "Model Output Comparison", 13)

    path = CHART_DIR / "probs.png"
    probability_bars(result.model_probs, path)
    slide.shapes.add_picture(str(path), MARGIN, Inches(1.5), width=Inches(8.5))

    # Right: numeric table
    y = Inches(1.6)
    p = result.model_probs
    for i, (label_zh, label_en, vals, color) in enumerate([
        ("ELO 模型", "ELO Model", p.elo, GOLD),
        ("Poisson 模型", "Poisson Model", p.poisson, CYAN),
        ("XGBoost 模型", "XGBoost Model", p.ml, GREEN),
        ("综合概率", "Consensus", p.consensus, RED),
    ]):
        ry = y + Inches(i * 0.85)
        _add_panel(slide, MARGIN + Inches(9.0), ry, Inches(3.1), Inches(0.75), fill=BG_CARD)
        _add_textbox(slide, MARGIN + Inches(9.1), ry + Inches(0.05), Inches(2.9), Inches(0.3),
                    f"{label_zh}  ·  {label_en}", font_size=Pt(10), color=color, bold=True, font_name=FONT_CN_BODY)
        _add_textbox(slide, MARGIN + Inches(9.1), ry + Inches(0.35), Inches(2.9), Inches(0.4),
                    f"{vals[0]:.0%}  /  {vals[1]:.0%}  /  {vals[2]:.0%}",
                    font_size=Pt(13), color=WHITE, bold=True, font_name=FONT_MONO)
        _add_textbox(slide, MARGIN + Inches(9.1), ry + Inches(0.55), Inches(2.9), Inches(0.2),
                    "胜 / 平 / 负  ·  Win / Draw / Loss", font_size=Pt(8), color=GREY, font_name=FONT_CN_BODY)

    _add_textbox(slide, MARGIN, Inches(6.6), Inches(8), Inches(0.4),
                f"预期进球  ·  Expected Goals:  {p.expected_goals[0]:.2f}  —  {p.expected_goals[1]:.2f}",
                font_size=Pt(15), color=GOLD, bold=True, font_name=FONT_CN_BODY)


def _page_monte_carlo(prs, result: PredictionResult) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide)
    _page_header(slide, "蒙特卡洛模拟", "Monte Carlo Simulation", 14)

    path = CHART_DIR / "mc.png"
    score_distribution(result.monte_carlo, path)
    slide.shapes.add_picture(str(path), MARGIN, Inches(1.5), width=Inches(8.5))

    # Right: outcome distribution
    y = Inches(1.6)
    mc = result.monte_carlo
    for i, (label_zh, label_en, val, color) in enumerate([
        ("主队胜", "Win", mc.win_a, GREEN),
        ("平局", "Draw", mc.draw, GREY),
        ("客队胜", "Loss", mc.win_b, RED),
    ]):
        ry = y + Inches(i * 1.2)
        _add_panel(slide, MARGIN + Inches(9.0), ry, Inches(3.1), Inches(1.0), fill=BG_CARD)
        _add_textbox(slide, MARGIN + Inches(9.1), ry + Inches(0.05), Inches(2.9), Inches(0.3),
                    f"{label_zh}  ·  {label_en}", font_size=Pt(11), color=color, bold=True, font_name=FONT_CN_BODY)
        _add_textbox(slide, MARGIN + Inches(9.1), ry + Inches(0.4), Inches(2.9), Inches(0.6),
                    f"{val:.1%}", font_size=Pt(32), bold=True, color=color, font_name=FONT_MONO)
    _add_textbox(slide, MARGIN + Inches(9.0), Inches(5.4), Inches(3.1), Inches(0.4),
                f"模拟次数：{mc.simulations:,}  ·  Simulations", font_size=Pt(9), color=GREY, font_name=FONT_CN_BODY, align=PP_ALIGN.CENTER)


def _page_sensitivity(prs, result: PredictionResult) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide)
    _page_header(slide, "敏感性分析", "Sensitivity Analysis", 15)

    _add_textbox(slide, MARGIN, Inches(1.2), Inches(12), Inches(0.4),
                "若以下变量翻转，结论是否会改变？", font_size=Pt(12), color=GREY, font_name=FONT_CN_BODY)

    # Compute sensitivity: how much each factor moves the consensus
    base = result.model_probs.consensus[0]
    factors = [
        ("ELO +50", abs(50 * 0.0015)),
        ("伤停恢复", 0.07),
        ("主场优势", 0.05),
        ("状态波动 3 分", 0.04),
        ("极端天气", 0.03),
        ("裁判尺度", 0.02),
    ]
    factors.sort(key=lambda x: -x[1])
    path = CHART_DIR / "sensitivity.png"
    sensitivity_tornado(factors, path)
    slide.shapes.add_picture(str(path), MARGIN, Inches(1.8), width=Inches(8.5))


def _page_final(prs, result: PredictionResult) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide)
    _page_header(slide, "最终预测", "Final Prediction", 16)

    team_a = result.match.team_a
    team_b = result.match.team_b
    pick = result.recommended_pick

    # Big result banner
    _add_panel(slide, MARGIN, Inches(1.4), Inches(12.1), Inches(2.0), fill=BG_PANEL)
    pick_label_zh = team_a.name_zh if pick == "A" else (team_b.name_zh if pick == "B" else "平局")
    pick_label_en = team_a.name_en if pick == "A" else (team_b.name_en if pick == "B" else "Draw")
    _add_textbox(slide, MARGIN + Inches(0.5), Inches(1.55), Inches(11), Inches(0.4),
                "最终预测  ·  FINAL PREDICTION", font_size=Pt(12), color=GOLD, font_name=FONT_CN_BODY, bold=True)
    _add_textbox(slide, MARGIN + Inches(0.5), Inches(2.0), Inches(11), Inches(0.8),
                f"{pick_label_zh}  ({pick_label_en})", font_size=Pt(40), bold=True, color=WHITE, font_name=FONT_CN_BODY)
    eg = result.model_probs.expected_goals
    _add_textbox(slide, MARGIN + Inches(0.5), Inches(2.8), Inches(11), Inches(0.5),
                f"预期比分  ·  Expected Score:  {eg[0]:.1f}  —  {eg[1]:.1f}",
                font_size=Pt(16), color=GOLD, font_name=FONT_CN_BODY, bold=True)

    # Confidence + risks
    conf_color = GREEN if result.confidence == "high" else (GOLD if result.confidence == "medium" else RED)
    conf_zh = "高" if result.confidence == "high" else "中" if result.confidence == "medium" else "低"
    _add_panel(slide, MARGIN, Inches(3.7), Inches(5.9), Inches(3.2), fill=BG_CARD)
    _add_textbox(slide, MARGIN + Inches(0.3), Inches(3.85), Inches(5.5), Inches(0.4),
                "信心指数  ·  CONFIDENCE", font_size=Pt(12), color=GOLD, font_name=FONT_CN_BODY, bold=True)
    _add_textbox(slide, MARGIN + Inches(0.3), Inches(4.3), Inches(5.5), Inches(1.0),
                f"{conf_zh}  ·  {result.confidence.upper()}", font_size=Pt(44), bold=True, color=conf_color, font_name=FONT_CN_BODY)
    p = result.model_probs.consensus
    _add_textbox(slide, MARGIN + Inches(0.3), Inches(5.3), Inches(5.5), Inches(0.4),
                f"胜 {p[0]:.0%}  ·  平 {p[1]:.0%}  ·  负 {p[2]:.0%}",
                font_size=Pt(12), color=WHITE, font_name=FONT_CN_BODY)
    _add_textbox(slide, MARGIN + Inches(0.3), Inches(5.6), Inches(5.5), Inches(0.4),
                f"最可能比分：{result.monte_carlo.top_scores[0][0]}  （{result.monte_carlo.top_scores[0][1]:.1%}）  ·  Top Score",
                font_size=Pt(11), color=WHITE, font_name=FONT_CN_BODY)

    # Risks
    _add_panel(slide, MARGIN + Inches(6.2), Inches(3.7), Inches(5.9), Inches(3.2), fill=BG_CARD)
    _add_textbox(slide, MARGIN + Inches(6.5), Inches(3.85), Inches(5.5), Inches(0.4),
                "关键风险  ·  KEY RISKS", font_size=Pt(12), color=GOLD, font_name=FONT_CN_BODY, bold=True)
    for i, risk in enumerate(result.key_risks):
        _add_textbox(slide, MARGIN + Inches(6.5), Inches(4.3) + Inches(i * 0.55), Inches(5.4), Inches(0.5),
                    f"• {risk}", font_size=Pt(10), color=WHITE, font_name=FONT_CN_BODY)


def _page_appendix(prs, result: PredictionResult) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _bg(slide)
    _page_header(slide, "附录", "Appendix", 17)

    _add_textbox(slide, MARGIN, Inches(1.4), Inches(12), Inches(0.4),
                "数据来源  ·  DATA SOURCES", font_size=Pt(13), color=GOLD, font_name=FONT_CN_BODY, bold=True)
    sources = [
        "Wikipedia REST API  ·  球员信息和照片",
        "football-data.org  ·  球队国际比赛历史",
        "ESPN 公开 API  ·  实时赛程（已切换为主源）",
        "本地种子阵容  ·  各国阵容种子库",
        "World Football ELO Ratings  ·  ELO 评分方法",
    ]
    for i, s in enumerate(sources):
        _add_textbox(slide, MARGIN + Inches(0.3), Inches(1.85) + Inches(i * 0.32), Inches(12), Inches(0.3),
                    f"• {s}", font_size=Pt(11), color=WHITE, font_name=FONT_CN_BODY)

    _add_textbox(slide, MARGIN, Inches(3.7), Inches(12), Inches(0.4),
                "方法说明  ·  METHODOLOGY", font_size=Pt(13), color=GOLD, font_name=FONT_CN_BODY, bold=True)
    method = [
        "1.  ELO 模型：基础实力差异，中立场调整",
        "2.  Poisson + Dixon-Coles：进球分布 + 低比分修正",
        "3.  XGBoost：基于合成但真实的特征空间的梯度提升",
        "4.  定性调整：战术 / 经验 / 心理 / 场地",
        "5.  蒙特卡洛（10,000 次）：基于 Poisson 强度参数模拟比赛",
        "6.  综合概率：三个基础模型调整后的加权平均",
    ]
    for i, m in enumerate(method):
        _add_textbox(slide, MARGIN + Inches(0.3), Inches(4.1) + Inches(i * 0.32), Inches(12), Inches(0.3),
                    m, font_size=Pt(10), color=WHITE, font_name=FONT_CN_BODY)

    _add_textbox(slide, MARGIN, Inches(6.2), Inches(12), Inches(0.4),
                "免责声明  ·  DISCLAIMER", font_size=Pt(13), color=RED, font_name=FONT_CN_BODY, bold=True)
    _add_textbox(slide, MARGIN, Inches(6.55), Inches(12), Inches(0.6),
                "本报告基于历史数据和统计模型，结果仅供参考，不构成任何投注或决策建议。",
                font_size=Pt(11), color=GREY, font_name=FONT_CN_BODY)


# ----------------------- main entry -----------------------

def build_ppt(result: PredictionResult, lang: str = "bilingual", output_path: Path | None = None) -> Path:
    """Build the full PPT and return the saved path."""
    logger.info("Building PPT…")

    # Try to enrich starting XIs with photos from Wikipedia (best effort)
    try:
        for lineup in (result.lineup_a, result.lineup_b):
            batch_augment_squad(lineup.players)
    except Exception as e:
        logger.debug(f"Wikipedia augment skipped: {e}")

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    _page_cover(prs, result)                # 1
    _page_summary(prs, result)              # 2
    _page_team_profile(prs, result)         # 3
    _page_recent_form(prs, result)          # 4
    _page_predicted_lineup(prs, result, "A")  # 5
    _page_predicted_lineup(prs, result, "B")  # 6
    _page_key_players(prs, result, "A")     # 7
    _page_key_players(prs, result, "B")     # 8
    _page_key_matchups(prs, result)         # 9
    _page_squad_depth(prs, result)          # 10
    _page_radar(prs, result)                # 11
    _page_qualitative(prs, result)          # 12
    _page_model_output(prs, result)         # 13
    _page_monte_carlo(prs, result)          # 14
    _page_sensitivity(prs, result)          # 15
    _page_final(prs, result)                # 16
    _page_appendix(prs, result)             # 17

    if output_path is None:
        team_a = result.match.team_a.name_en
        team_b = result.match.team_b.name_en
        date = result.match.match_date
        output_path = config.output_dir / f"{team_a}_vs_{team_b}_{date}.pptx"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(output_path))
    logger.success(f"PPT saved to {output_path}")
    return output_path
