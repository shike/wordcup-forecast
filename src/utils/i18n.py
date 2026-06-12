"""Bilingual (Chinese / English) text dictionary.

Lookup returns both languages, used in PPT for side-by-side layout.
"""
from __future__ import annotations

T = {
    # cover
    "cover_title": {"zh": "世界杯比赛预测报告", "en": "World Cup Match Forecast Report"},
    "match": {"zh": "比赛", "en": "Match"},
    "vs": {"zh": "对阵", "en": "vs"},
    "stage": {"zh": "阶段", "en": "Stage"},
    "date": {"zh": "比赛日期", "en": "Date"},
    "venue": {"zh": "比赛场地", "en": "Venue"},
    "forecast_time": {"zh": "预测时间", "en": "Forecast Time"},
    "generated_at": {"zh": "生成时间", "en": "Generated"},
    "model_version_label": {"zh": "模型版本", "en": "Model"},

    # executive summary
    "executive_summary": {"zh": "执行摘要", "en": "Executive Summary"},
    "win_prob": {"zh": "胜", "en": "Win"},
    "draw_prob": {"zh": "平", "en": "Draw"},
    "loss_prob": {"zh": "负", "en": "Loss"},
    "expected_score": {"zh": "预期比分", "en": "Expected Score"},
    "confidence": {"zh": "信心指数", "en": "Confidence"},
    "high": {"zh": "高", "en": "High"},
    "medium": {"zh": "中", "en": "Medium"},
    "low": {"zh": "低", "en": "Low"},
    "recommended_pick": {"zh": "推荐结果", "en": "Recommended Pick"},
    "top_scores_label": {"zh": "最可能比分", "en": "Top Scores"},

    # team profile
    "team_profile": {"zh": "球队档案", "en": "Team Profile"},
    "fifa_ranking": {"zh": "FIFA 排名", "en": "FIFA Ranking"},
    "elo": {"zh": "ELO 评分", "en": "ELO Rating"},
    "coach": {"zh": "主教练", "en": "Head Coach"},
    "squad_value": {"zh": "阵容身价", "en": "Squad Value"},
    "captain": {"zh": "队长", "en": "Captain"},
    "avg_age": {"zh": "平均年龄", "en": "Average Age"},
    "confederation_label": {"zh": "所属足联", "en": "Confederation"},
    "kit_color_label": {"zh": "主队服颜色", "en": "Kit Color"},

    # h2h
    "head_to_head": {"zh": "历史交锋", "en": "Head-to-Head"},
    "total_meetings": {"zh": "总交锋", "en": "Total Meetings"},
    "wins": {"zh": "胜", "en": "Wins"},
    "draws": {"zh": "平", "en": "Draws"},
    "losses": {"zh": "负", "en": "Losses"},
    "last_meetings": {"zh": "近 5 次交锋", "en": "Last 5 Meetings"},

    # form
    "recent_form": {"zh": "近期状态", "en": "Recent Form"},
    "last_10": {"zh": "近 10 场", "en": "Last 10 Matches"},
    "points_per_game": {"zh": "场均积分", "en": "Points / Game"},
    "goals_per_game": {"zh": "场均进球", "en": "Goals / Game"},
    "conceded_per_game": {"zh": "场均失球", "en": "Conceded / Game"},
    "goals_per_game_short": {"zh": "进球", "en": "Goals"},
    "conceded_per_game_short": {"zh": "失球", "en": "Conceded"},
    "xG_label": {"zh": "xG", "en": "xG"},
    "clean_sheet_pct": {"zh": "零封率", "en": "Clean Sheet %"},
    "key_passes_label": {"zh": "关键传球", "en": "Key Passes"},
    "shot_accuracy_label": {"zh": "射门精度", "en": "Shot Accuracy"},
    "tackles_label": {"zh": "抢断", "en": "Tackles"},
    "interceptions_label": {"zh": "拦截", "en": "Interceptions"},
    "form_W": {"zh": "胜", "en": "W"},
    "form_D": {"zh": "平", "en": "D"},
    "form_L": {"zh": "负", "en": "L"},
    "last10_summary": {"zh": "近 10 场战绩", "en": "Last 10 Matches"},

    # lineup
    "predicted_lineup": {"zh": "预测首发", "en": "Predicted Starting XI"},
    "formation": {"zh": "阵型", "en": "Formation"},
    "starting_xi": {"zh": "首发 11 人", "en": "Starting XI"},
    "bench": {"zh": "替补席", "en": "Bench"},
    "absent": {"zh": "缺阵", "en": "Absent"},
    "bench_label": {"zh": "替补", "en": "Bench"},

    # players
    "key_players": {"zh": "核心球员", "en": "Key Players"},
    "position": {"zh": "位置", "en": "Position"},
    "age": {"zh": "年龄", "en": "Age"},
    "club": {"zh": "俱乐部", "en": "Club"},
    "caps": {"zh": "国家队出场", "en": "Caps"},
    "goals": {"zh": "进球", "en": "Goals"},
    "rating": {"zh": "评分", "en": "Rating"},
    "preferred_foot": {"zh": "惯用脚", "en": "Foot"},
    "height": {"zh": "身高", "en": "Height"},
    "foot": {"zh": "惯用脚", "en": "Foot"},
    "stat_pac": {"zh": "速度", "en": "Pace"},
    "stat_sho": {"zh": "射门", "en": "Shooting"},
    "stat_pas": {"zh": "传球", "en": "Passing"},
    "stat_dri": {"zh": "盘带", "en": "Dribbling"},
    "stat_def": {"zh": "防守", "en": "Defending"},
    "stat_phy": {"zh": "身体", "en": "Physical"},

    # matchups
    "key_matchups": {"zh": "关键对位 1v1", "en": "Key Matchups"},
    "matchup_striker_v_cb": {"zh": "箭头对决 · 锋线尖刀 vs 中后卫", "en": "Star Striker vs Centre-Back"},
    "matchup_playmaker_v_anchor": {"zh": "中场大脑 · 创造者 vs 清道夫", "en": "Playmaker vs Anchor"},
    "matchup_winger_v_fullback": {"zh": "边路狂飙 · 边锋 vs 边后卫", "en": "Winger vs Fullback"},
    "matchup_keeper_duel": {"zh": "最后一道防线 · 门将对决", "en": "Last Line · Keeper Duel"},

    # depth
    "squad_depth": {"zh": "阵容深度", "en": "Squad Depth"},
    "starter_strength": {"zh": "首发战力", "en": "Starter Strength"},
    "bench_strength": {"zh": "替补战力", "en": "Bench Strength"},
    "depth_chart": {"zh": "首发 vs 替补战力", "en": "Starter vs Bench Strength"},
    "strength_index": {"zh": "战力指数", "en": "Strength Index"},

    # attack/defense
    "attacking": {"zh": "进攻能力", "en": "Attacking"},
    "defending": {"zh": "防守能力", "en": "Defending"},
    "team_capabilities": {"zh": "球队能力对比", "en": "Team Capabilities"},
    "xg": {"zh": "xG 期望进球", "en": "xG"},
    "xga": {"zh": "xGA 期望失球", "en": "xGA"},
    "clean_sheet_rate": {"zh": "零封率", "en": "Clean Sheet Rate"},
    "key_passes": {"zh": "关键传球", "en": "Key Passes"},
    "shot_accuracy": {"zh": "射门精度", "en": "Shot Accuracy"},
    "tackles": {"zh": "抢断", "en": "Tackles"},
    "interceptions": {"zh": "拦截", "en": "Interceptions"},

    # injuries
    "injuries": {"zh": "伤停名单", "en": "Injuries"},
    "impact": {"zh": "影响", "en": "Impact"},
    "critical": {"zh": "关键", "en": "Critical"},
    "moderate": {"zh": "中等", "en": "Moderate"},
    "minor": {"zh": "轻微", "en": "Minor"},
    "no_injuries": {"zh": "无伤停", "en": "None reported"},
    "injury_label": {"zh": "伤停", "en": "Injuries"},

    # qualitative
    "qualitative_factors": {"zh": "定性因子", "en": "Qualitative Factors"},
    "tactical": {"zh": "战术", "en": "Tactical"},
    "experience": {"zh": "大赛经验", "en": "Experience"},
    "psychology": {"zh": "心理因素", "en": "Psychology"},
    "venue_factor": {"zh": "场地因素", "en": "Venue Factor"},
    "schedule": {"zh": "赛程密度", "en": "Schedule"},

    # model
    "model_output": {"zh": "模型输出对比", "en": "Model Output"},
    "elo_model": {"zh": "ELO 模型", "en": "ELO Model"},
    "poisson_model": {"zh": "Poisson 模型", "en": "Poisson Model"},
    "ml_model": {"zh": "XGBoost 模型", "en": "XGBoost Model"},
    "consensus": {"zh": "综合概率", "en": "Consensus"},
    "model_comparison": {"zh": "三模型概率对比", "en": "Model Probability Comparison"},
    "probability": {"zh": "概率", "en": "Probability"},
    "win": {"zh": "胜", "en": "Win"},
    "draw": {"zh": "平", "en": "Draw"},
    "loss": {"zh": "负", "en": "Loss"},
    "win_draw_loss": {"zh": "胜 / 平 / 负", "en": "Win / Draw / Loss"},
    "expected_goals_label": {"zh": "预期进球", "en": "Expected Goals"},

    # monte carlo
    "monte_carlo": {"zh": "蒙特卡洛模拟", "en": "Monte Carlo Simulation"},
    "simulations": {"zh": "模拟次数", "en": "Simulations"},
    "top_scores": {"zh": "最可能比分 TOP 5", "en": "Top 5 Most Likely Scores"},
    "probability_distribution": {"zh": "比分概率分布", "en": "Score Probability Distribution"},
    "mc_chart_title": {"zh": "最可能比分（蒙特卡洛模拟）", "en": "Most Likely Scores (Monte Carlo)"},
    "mc_sim_count": {"zh": "模拟次数", "en": "Simulations"},

    # sensitivity
    "sensitivity": {"zh": "敏感性分析", "en": "Sensitivity Analysis"},
    "sensitivity_desc": {
        "zh": "若以下变量翻转，结论是否会改变？",
        "en": "Would the conclusion flip if these variables changed?",
    },
    "sensitivity_impact": {"zh": "对胜率的影响（百分点）", "en": "Impact on win probability (pp)"},

    # final
    "final_prediction": {"zh": "最终预测", "en": "Final Prediction"},
    "key_risks": {"zh": "关键风险", "en": "Key Risks"},
    "top_score": {"zh": "最可能比分", "en": "Top Score"},
    "confidence_label": {"zh": "信心", "en": "Confidence"},
    "risk_label": {"zh": "关键风险", "en": "Key Risks"},

    # appendix
    "appendix": {"zh": "附录", "en": "Appendix"},
    "data_sources": {"zh": "数据来源", "en": "Data Sources"},
    "methodology": {"zh": "方法说明", "en": "Methodology"},
    "model_version": {"zh": "模型版本", "en": "Model Version"},
    "disclaimer": {"zh": "免责声明", "en": "Disclaimer"},
    "disclaimer_text": {
        "zh": "本报告基于历史数据和统计模型，结果仅供参考，不构成任何投注或决策建议。",
        "en": "This report is based on historical data and statistical models. "
               "Results are for reference only and do not constitute betting or decision advice.",
    },

    # misc / chart labels
    "goals_label": {"zh": "进球", "en": "Goals"},
    "xG_axis": {"zh": "xG 期望进球", "en": "xG"},
    "clean_sheet": {"zh": "零封", "en": "Clean Sheet"},
    "stadium": {"zh": "场地", "en": "Venue"},
    "status": {"zh": "状态", "en": "Status"},
    "team_a_short": {"zh": "主队", "en": "Team A"},
    "team_b_short": {"zh": "客队", "en": "Team B"},

    # generic
    "page": {"zh": "第", "en": "Page"},
    "of": {"zh": "页 / 共", "en": "of"},
    "team_a": {"zh": "主队", "en": "Team A"},
    "team_b": {"zh": "客队", "en": "Team B"},
}


def tr(key: str, lang: str = "bilingual") -> str:
    """Return translated text. lang in {zh, en, bilingual}."""
    entry = T.get(key, {"zh": key, "en": key})
    if lang == "bilingual":
        return f"{entry['zh']} / {entry['en']}"
    return entry.get(lang, entry["en"])


def tr_zh(key: str) -> str:
    """Always return the Chinese text (for Chinese-primary layout)."""
    entry = T.get(key, {"zh": key, "en": key})
    return entry.get("zh", key)


def tr_en(key: str) -> str:
    """Always return the English text."""
    entry = T.get(key, {"zh": key, "en": key})
    return entry.get("en", key)


def tr_pair(key: str) -> tuple[str, str]:
    """Return (zh, en) tuple for side-by-side layout."""
    entry = T.get(key, {"zh": key, "en": key})
    return entry["zh"], entry["en"]
