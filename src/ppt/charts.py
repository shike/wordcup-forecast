"""Matplotlib chart generators.  All figures use the dark sports-data palette.

Each function returns a BytesIO that python-pptx can embed.
"""
from __future__ import annotations

import io
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from src.utils.models import (
    ModelProbabilities,
    MonteCarloResult,
    TeamStats,
    QualitativeFactors,
)


# Match the PPT palette so charts feel native
BG = "#0A1628"
PANEL = "#12223C"
TEXT = "#F5F7FA"
GOLD = "#FFB627"
CYAN = "#00D4FF"
GREEN = "#6EE08E"
RED = "#FF4D6D"
GREY = "#9AB0C8"


def _setup_axis(ax) -> None:
    ax.set_facecolor(PANEL)
    ax.tick_params(colors=GREY, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color("#2A3F60")
    ax.grid(True, color="#2A3F60", linewidth=0.5, alpha=0.5)


def probability_bars(probs: ModelProbabilities, save_path: Path) -> Path:
    """Three-model probability bar chart for team A."""
    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor=BG)
    _setup_axis(ax)
    models = ["ELO", "Poisson", "XGBoost", "Consensus"]
    win = [probs.elo[0], probs.poisson[0], probs.ml[0], probs.consensus[0]]
    draw = [probs.elo[1], probs.poisson[1], probs.ml[1], probs.consensus[1]]
    loss = [probs.elo[2], probs.poisson[2], probs.ml[2], probs.consensus[2]]

    x = np.arange(len(models))
    w = 0.25
    ax.bar(x - w, win, w, color=GREEN, label="Win")
    ax.bar(x, draw, w, color=GREY, label="Draw")
    ax.bar(x + w, loss, w, color=RED, label="Loss")
    ax.set_xticks(x)
    ax.set_xticklabels(models, color=TEXT, fontsize=11)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Probability", color=GREY)
    ax.set_title("Model Output Comparison", color=TEXT, fontsize=14, weight="bold", pad=12)
    ax.legend(loc="upper right", facecolor=PANEL, edgecolor="#2A3F60", labelcolor=TEXT)
    fig.tight_layout()
    fig.savefig(save_path, dpi=160, facecolor=BG)
    plt.close(fig)
    return save_path


def score_distribution(mc: MonteCarloResult, save_path: Path) -> Path:
    """Top 10 score bar chart from Monte Carlo distribution."""
    fig, ax = plt.subplots(figsize=(9, 4.5), facecolor=BG)
    _setup_axis(ax)
    items = sorted(mc.distribution.items(), key=lambda kv: -kv[1])[:10]
    labels = [k for k, _ in items]
    values = [v * 100 for _, v in items]
    colors = [GOLD if i == 0 else CYAN if i < 3 else "#2A486F" for i in range(len(labels))]
    bars = ax.barh(labels[::-1], values[::-1], color=colors[::-1])
    for bar, val in zip(bars, values[::-1]):
        ax.text(val + 0.3, bar.get_y() + bar.get_height() / 2, f"{val:.1f}%",
                va="center", color=TEXT, fontsize=9)
    ax.set_xlabel("Probability (%)", color=GREY)
    ax.set_title("Most Likely Scores (Monte Carlo)", color=TEXT, fontsize=14, weight="bold", pad=12)
    ax.set_xlim(0, max(values) * 1.18)
    fig.tight_layout()
    fig.savefig(save_path, dpi=160, facecolor=BG)
    plt.close(fig)
    return save_path


def radar_chart(stats_a: TeamStats, stats_b: TeamStats, save_path: Path, lang: str = "bilingual") -> Path:
    """6-axis radar chart comparing attack/defence capabilities."""
    labels_zh = ["进球", "xG", "关键传球", "零封率", "抢断", "拦截"]
    labels_en = ["Goals", "xG", "Key Passes", "Clean Sheet", "Tackles", "Interceptions"]
    categories = list(range(6))
    angles = [n / 6 * 2 * np.pi for n in categories]
    angles += angles[:1]

    def norm(values, maxes):
        return [v / m for v, m in zip(values, maxes)]

    a_raw = [stats_a.goals_per_game, stats_a.xg_per_game, stats_a.key_passes_per_game,
             stats_a.clean_sheet_rate, stats_a.tackles_per_game, stats_a.interceptions_per_game]
    b_raw = [stats_b.goals_per_game, stats_b.xg_per_game, stats_b.key_passes_per_game,
             stats_b.clean_sheet_rate, stats_b.tackles_per_game, stats_b.interceptions_per_game]
    # Use the max of corresponding axes (element-wise) with a small floor
    maxes = [max(a, b, 0.1) for a, b in zip(a_raw, b_raw)]

    a_values = norm(a_raw, maxes)
    b_values = norm(b_raw, maxes)

    a_values += a_values[:1]
    b_values += b_values[:1]

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw={"projection": "polar"}, facecolor=BG)
    ax.set_facecolor(PANEL)
    ax.plot(angles, a_values, color=GOLD, linewidth=2, label="A")
    ax.fill(angles, a_values, color=GOLD, alpha=0.25)
    ax.plot(angles, b_values, color=CYAN, linewidth=2, label="B")
    ax.fill(angles, b_values, color=CYAN, alpha=0.25)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(
        [f"{zh}\n{en}" for zh, en in zip(labels_zh, labels_en)], color=TEXT, fontsize=9
    )
    ax.tick_params(colors=GREY)
    ax.set_yticklabels([])
    ax.spines["polar"].set_color("#2A3F60")
    ax.grid(color="#2A3F60", alpha=0.5)
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.1), facecolor=PANEL, edgecolor="#2A3F60", labelcolor=TEXT)
    ax.set_title("Team Comparison", color=TEXT, fontsize=13, weight="bold", pad=18)
    fig.tight_layout()
    fig.savefig(save_path, dpi=160, facecolor=BG)
    plt.close(fig)
    return save_path


def qualitative_radar(
    qa: QualitativeFactors, qb: QualitativeFactors, save_path: Path
) -> Path:
    """5-axis qualitative radar (tactical, experience, psychology, venue, schedule)."""
    labels_zh = ["战术", "经验", "心理", "场地", "赛程"]
    labels_en = ["Tactical", "Experience", "Psychology", "Venue", "Schedule"]
    a_values = [qa.tactical, qa.experience, qa.psychology, qa.venue_factor, qa.schedule]
    b_values = [qb.tactical, qb.experience, qb.psychology, qb.venue_factor, qb.schedule]
    categories = list(range(5))
    angles = [n / 5 * 2 * np.pi for n in categories]
    angles += angles[:1]
    a_values = a_values + a_values[:1]
    b_values = b_values + b_values[:1]

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw={"projection": "polar"}, facecolor=BG)
    ax.set_facecolor(PANEL)
    ax.plot(angles, a_values, color=GOLD, linewidth=2, label="A")
    ax.fill(angles, a_values, color=GOLD, alpha=0.25)
    ax.plot(angles, b_values, color=CYAN, linewidth=2, label="B")
    ax.fill(angles, b_values, color=CYAN, alpha=0.25)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(
        [f"{zh}\n{en}" for zh, en in zip(labels_zh, labels_en)], color=TEXT, fontsize=10
    )
    ax.set_ylim(0, 10)
    ax.set_yticks([2, 4, 6, 8, 10])
    ax.set_yticklabels(["2", "4", "6", "8", "10"], color=GREY, fontsize=8)
    ax.tick_params(colors=GREY)
    ax.spines["polar"].set_color("#2A3F60")
    ax.grid(color="#2A3F60", alpha=0.5)
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.1), facecolor=PANEL, edgecolor="#2A3F60", labelcolor=TEXT)
    ax.set_title("Qualitative Factors", color=TEXT, fontsize=13, weight="bold", pad=18)
    fig.tight_layout()
    fig.savefig(save_path, dpi=160, facecolor=BG)
    plt.close(fig)
    return save_path


def form_trend(
    last_10: list[str], save_path: Path, label: str = "Team"
) -> Path:
    """Recent form line chart (rolling points).  last_10 = list of W/D/L chars."""
    pts = [3 if r == "W" else 1 if r == "D" else 0 for r in last_10]
    cum = np.cumsum(pts)
    fig, ax = plt.subplots(figsize=(8, 3.5), facecolor=BG)
    _setup_axis(ax)
    ax.plot(range(1, len(cum) + 1), cum, color=GOLD, linewidth=2.5, marker="o", markersize=6)
    ax.fill_between(range(1, len(cum) + 1), cum, color=GOLD, alpha=0.15)
    ax.set_xlim(0.5, 10.5)
    ax.set_ylim(0, max(cum) + 3)
    ax.set_xlabel("Match #", color=GREY)
    ax.set_ylabel("Cumulative Points", color=GREY)
    ax.set_title(f"Recent Form · {label}", color=TEXT, fontsize=13, weight="bold", pad=10)
    fig.tight_layout()
    return fig


def depth_bars(
    a_starter: float, a_bench: float, b_starter: float, b_bench: float, save_path: Path
) -> Path:
    fig, ax = plt.subplots(figsize=(7, 3.5), facecolor=BG)
    _setup_axis(ax)
    groups = ["Starter", "Bench"]
    x = np.arange(len(groups))
    w = 0.35
    ax.bar(x - w / 2, [a_starter, a_bench], w, color=GOLD, label="A")
    ax.bar(x + w / 2, [b_starter, b_bench], w, color=CYAN, label="B")
    ax.set_xticks(x)
    ax.set_xticklabels(groups, color=TEXT)
    ax.set_ylim(0, 110)
    ax.set_ylabel("Strength Index", color=GREY)
    ax.legend(facecolor=PANEL, edgecolor="#2A3F60", labelcolor=TEXT)
    ax.set_title("Squad Depth", color=TEXT, fontsize=13, weight="bold", pad=10)
    fig.tight_layout()
    fig.savefig(save_path, dpi=160, facecolor=BG)
    plt.close(fig)
    return save_path


def sensitivity_tornado(factors: list[tuple[str, float]], save_path: Path) -> Path:
    """factors: [(name, swing), …] in descending swing order."""
    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor=BG)
    _setup_axis(ax)
    names = [f[0] for f in factors]
    values = [f[1] for f in factors]
    y = np.arange(len(names))
    ax.barh(y, values, color=GOLD)
    ax.set_yticks(y)
    ax.set_yticklabels(names, color=TEXT)
    ax.invert_yaxis()
    ax.set_xlabel("Impact on win probability (pp)", color=GREY)
    ax.set_title("Sensitivity Analysis", color=TEXT, fontsize=13, weight="bold", pad=10)
    fig.tight_layout()
    fig.savefig(save_path, dpi=160, facecolor=BG)
    plt.close(fig)
    return save_path
