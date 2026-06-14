"""Pydantic data models for type-safe prediction pipeline."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Team(BaseModel):
    code: str
    name_en: str
    name_zh: str
    fifa_ranking: int
    elo: float
    coach: str
    coach_zh: str = ""
    captain: str
    captain_zh: str = ""
    home_kit_color: str = "#FFFFFF"
    confederation: str = ""


class Player(BaseModel):
    id: str
    name: str
    name_zh: str | None = None
    position: Literal["GK", "RB", "CB", "LB", "CDM", "CM", "CAM", "RW", "LW", "ST", "CF"]
    secondary_positions: list[str] = Field(default_factory=list)
    number: int = 0
    age: int = 25
    club: str = ""
    caps: int = 0
    goals: int = 0
    assists: int = 0
    rating: float = 7.0
    preferred_foot: Literal["L", "R", "B"] = "R"
    height_cm: int = 180
    photo_path: str | None = None
    wikipedia_url: str | None = None

    def display_name(self, lang: str = "bilingual") -> str:
        if lang == "zh" and self.name_zh:
            return self.name_zh
        if lang == "en":
            return self.name
        # bilingual: Chinese first (or fallback to English if no name_zh)
        primary = self.name_zh or self.name
        return f"{primary}  ·  {self.name}"

    def display_name_cn(self) -> str:
        """Return the Chinese name, falling back to English if not available."""
        return self.name_zh or self.name


class Formation(BaseModel):
    name: str
    code: str
    positions: list[str]  # 11 position slots in order: GK, defenders, midfielders, forwards
    coordinates: list[tuple[float, float]]  # normalized (x, y) on the pitch
    description_zh: str
    description_en: str


class Lineup(BaseModel):
    team_code: str
    formation: str
    players: list[Player]
    bench: list[Player] = Field(default_factory=list)
    injured: list[Player] = Field(default_factory=list)


class InjuryReport(BaseModel):
    player: Player
    status: Literal["out", "doubtful", "minor"]
    impact: Literal["critical", "moderate", "minor"]
    reason: str = ""


class TeamStats(BaseModel):
    team_code: str
    last_10_wins: int = 0
    last_10_draws: int = 0
    last_10_losses: int = 0
    goals_per_game: float = 1.4
    conceded_per_game: float = 1.0
    xg_per_game: float = 1.5
    xga_per_game: float = 1.1
    clean_sheet_rate: float = 0.30
    key_passes_per_game: float = 10.0
    shot_accuracy: float = 0.40
    tackles_per_game: float = 18.0
    interceptions_per_game: float = 12.0
    avg_player_rating: float = 7.0
    starter_strength: float = 80.0
    bench_strength: float = 60.0
    # #6 VAR / 裁判相关
    cards_per_game: float = 1.8           # 黄红牌数
    fouls_per_game: float = 11.0
    # #9 赛程密度
    days_since_last_match: int = 6
    matches_in_last_7_days: int = 1
    # #10 定位球 / 持球
    set_piece_goals_pct: float = 0.25    # 定位球进球占比
    possession_avg: float | None = None
    pressing_intensity: float = 0.50      # 0-1, 越高越积极


class QualitativeFactors(BaseModel):
    tactical: float = 7.0
    experience: float = 7.0
    psychology: float = 7.0
    venue_factor: float = 7.0
    schedule: float = 7.0


class MatchInput(BaseModel):
    team_a: Team
    team_b: Team
    match_date: str
    stage: Literal["group", "round_of_16", "quarterfinal", "semifinal", "final", "third_place"] = "group"
    venue: str = "TBD"
    is_neutral: bool = True


class ModelProbabilities(BaseModel):
    """Single-model output with transparency fields.

    The legacy three-model fields (elo, poisson, ml, consensus, divergence,
    market_consensus_gap) have been removed. The prediction pipeline now uses
    one Dixon-Coles model built from real data.
    """
    primary_model: str = "dixon_coles_xg"
    win_draw_loss: tuple[float, float, float]  # win, draw, loss for team_a
    expected_goals: tuple[float, float]  # (a, b)
    confidence: Literal["high", "medium", "low"] = "medium"

    # Transparency: how much real data was available
    data_quality: float = 0.0  # 0.0-1.0, share of inputs coming from real data
    sample_size_a: int = 0
    sample_size_b: int = 0
    elo_prior_weight: float = 0.0  # 0.0 = pure stats, 1.0 = pure ELO

    # Optional backtesting metadata
    model_rps: float | None = None
    calibration_error: float | None = None


class MonteCarloResult(BaseModel):
    simulations: int
    win_a: float
    draw: float
    win_b: float
    top_scores: list[tuple[str, float]]  # (score_str, prob)
    distribution: dict[str, float]  # score -> prob
    extra_time_prob: float = 0.0
    penalties_prob: float = 0.0

    @property
    def predicted_score(self) -> str:
        """The single most likely exact score, e.g. '2-1'.

        Biases the result to the match favourite: when the consensus pick
        is a team win, returns the highest-probability score in that
        direction; for a draw, returns the most likely X-X score.
        """
        if not self.distribution:
            return "0-0"
        # The caller passes consensus pick separately; for the property we
        # fall back to the raw mode.
        if self.top_scores:
            return self.top_scores[0][0]
        return max(self.distribution.items(), key=lambda kv: kv[1])[0]

    def predicted_score_for(self, pick: str) -> str:
        """The most likely score that matches the consensus pick.

        pick ∈ {'A', 'B', 'draw'}.
        """
        if not self.distribution:
            return "0-0"
        candidates = []
        for score, prob in self.distribution.items():
            try:
                a, b = score.split("-")
                a, b = int(a), int(b)
            except (ValueError, AttributeError):
                continue
            outcome = "A" if a > b else ("B" if b > a else "draw")
            if outcome == pick:
                candidates.append((score, prob))
        if candidates:
            return max(candidates, key=lambda kv: kv[1])[0]
        # No score matched the requested outcome (e.g. caller asked for "draw"
        # but the distribution has no drawn score). Return the top score.
        if self.top_scores:
            return self.top_scores[0][0]
        return "0-0"

    def split_goals(self, score: str | None = None) -> tuple[int, int]:
        """Parse a 'a-b' score string into (goals_a, goals_b)."""
        s = score or self.predicted_score
        try:
            a, b = s.split("-")
            return int(a), int(b)
        except Exception:
            return 0, 0

    def score_outcome(self, score: str | None = None) -> str:
        """Return 'A', 'B', or 'draw' for the parsed score."""
        a, b = self.split_goals(score)
        if a > b:
            return "A"
        if b > a:
            return "B"
        return "draw"


class Matchup(BaseModel):
    title_zh: str
    title_en: str
    player_a: Player
    player_b: Player
    stat_pairs: list[tuple[str, str, str, str]]  # (label_zh, label_en, val_a, val_b)


class PredictionResult(BaseModel):
    match: MatchInput
    team_a_stats: TeamStats
    team_b_stats: TeamStats
    qualitative_a: QualitativeFactors
    qualitative_b: QualitativeFactors
    injuries_a: list[InjuryReport]
    injuries_b: list[InjuryReport]
    lineup_a: Lineup
    lineup_b: Lineup
    model_probs: ModelProbabilities
    monte_carlo: MonteCarloResult
    key_matchups: list[Matchup]
    recommended_pick: Literal["A", "B", "draw"]
    confidence: Literal["high", "medium", "low"]
    key_risks: list[str]
    pre_match_news: list[str] = Field(default_factory=list)
