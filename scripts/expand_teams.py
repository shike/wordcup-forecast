"""Expand data/teams.json with seeds for teams that have match data in the
warehouse but no entry in the seed file.

FIFA ranking and ELO values reflect the November 2022 World Cup reference
point. Coaches/captains reflect the head coach and captain on file for
each national team around that period. Operator should review and
override for current 2026 World Cup when final squad data is available.
"""
from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from src.utils.config import config
from src.data.repository import MatchRepository


# Seeds: code -> dict of seed fields
# Source: FIFA rankings as of 2022-11; coaches/captains publicly announced
# for the 2022 World Cup cycle.
NEW_TEAM_SEEDS: dict[str, dict] = {
    "CMR": {
        "name_en": "Cameroon", "name_zh": "喀麦隆",
        "fifa_ranking": 33, "elo": 1700, "confederation": "CAF",
        "coach": "Rigobert Song", "coach_zh": "里戈贝尔·宋",
        "captain": "Vincent Aboubakar", "captain_zh": "文森特·阿布巴卡尔",
        "home_kit_color": "#007A33",
    },
    "COL": {
        "name_en": "Colombia", "name_zh": "哥伦比亚",
        "fifa_ranking": 17, "elo": 1880, "confederation": "CONMEBOL",
        "coach": "Néstor Lorenzo", "coach_zh": "内斯托尔·洛伦索",
        "captain": "Radamel Falcao", "captain_zh": "拉达梅尔·法尔考",
        "home_kit_color": "#FCD116",
    },
    "CRC": {
        "name_en": "Costa Rica", "name_zh": "哥斯达黎加",
        "fifa_ranking": 31, "elo": 1720, "confederation": "CONCACAF",
        "coach": "Luis Fernando Suárez", "coach_zh": "路易斯·费尔南多·苏亚雷斯",
        "captain": "Keylor Navas", "captain_zh": "凯洛尔·纳瓦斯",
        "home_kit_color": "#002B7F",
    },
    "CRO": {
        "name_en": "Croatia", "name_zh": "克罗地亚",
        "fifa_ranking": 12, "elo": 1920, "confederation": "UEFA",
        "coach": "Zlatko Dalić", "coach_zh": "兹拉特科·达利奇",
        "captain": "Luka Modrić", "captain_zh": "卢卡·莫德里奇",
        "home_kit_color": "#FF0000",
    },
    "DEN": {
        "name_en": "Denmark", "name_zh": "丹麦",
        "fifa_ranking": 18, "elo": 1870, "confederation": "UEFA",
        "coach": "Kasper Hjulmand", "coach_zh": "卡斯帕·尤尔曼",
        "captain": "Simon Kjær", "captain_zh": "西蒙·克亚尔",
        "home_kit_color": "#C8102E",
    },
    "ECU": {
        "name_en": "Ecuador", "name_zh": "厄瓜多尔",
        "fifa_ranking": 24, "elo": 1820, "confederation": "CONMEBOL",
        "coach": "Gustavo Alfaro", "coach_zh": "古斯塔沃·阿尔法罗",
        "captain": "Enner Valencia", "captain_zh": "恩纳·瓦伦西亚",
        "home_kit_color": "#FFD100",
    },
    "GHA": {
        "name_en": "Ghana", "name_zh": "加纳",
        "fifa_ranking": 26, "elo": 1780, "confederation": "CAF",
        "coach": "Otto Addo", "coach_zh": "奥托·阿多",
        "captain": "André Ayew", "captain_zh": "安德烈·阿尤",
        "home_kit_color": "#FCD116",
    },
    "IRN": {
        "name_en": "Iran", "name_zh": "伊朗",
        "fifa_ranking": 20, "elo": 1830, "confederation": "AFC",
        "coach": "Carlos Queiroz", "coach_zh": "卡洛斯·奎罗斯",
        "captain": "Alireza Jahanbakhsh", "captain_zh": "阿里雷扎·贾汉巴赫什",
        "home_kit_color": "#FFFFFF",
    },
    "KSA": {
        "name_en": "Saudi Arabia", "name_zh": "沙特阿拉伯",
        "fifa_ranking": 45, "elo": 1670, "confederation": "AFC",
        "coach": "Hervé Renard", "coach_zh": "埃尔韦·勒纳尔",
        "captain": "Salman Al-Faraj", "captain_zh": "萨尔曼·阿尔-法拉吉",
        "home_kit_color": "#006C35",
    },
    "ISL": {
        "name_en": "Iceland", "name_zh": "冰岛",
        "fifa_ranking": 62, "elo": 1650, "confederation": "UEFA",
        "coach": "Age Hareide", "coach_zh": "阿格·哈雷德",
        "captain": "Aron Gunnarsson", "captain_zh": "阿隆·古纳尔松",
        "home_kit_color": "#0033A0",
    },
    "NGA": {
        "name_en": "Nigeria", "name_zh": "尼日利亚",
        "fifa_ranking": 35, "elo": 1700, "confederation": "CAF",
        "coach": "José Peseiro", "coach_zh": "若泽·佩塞罗",
        "captain": "Ahmed Musa", "captain_zh": "艾哈迈德·穆萨",
        "home_kit_color": "#008753",
    },
    "PAN": {
        "name_en": "Panama", "name_zh": "巴拿马",
        "fifa_ranking": 53, "elo": 1660, "confederation": "CONCACAF",
        "coach": "Thomas Christiansen", "coach_zh": "托马斯·克里斯蒂安森",
        "captain": "Román Torres", "captain_zh": "罗曼·托雷斯",
        "home_kit_color": "#DA121A",
    },
    "PER": {
        "name_en": "Peru", "name_zh": "秘鲁",
        "fifa_ranking": 21, "elo": 1830, "confederation": "CONMEBOL",
        "coach": "Juan Reynoso", "coach_zh": "胡安·雷纳索",
        "captain": "Paolo Guerrero", "captain_zh": "保罗·格雷罗",
        "home_kit_color": "#FFFFFF",
    },
    "POL": {
        "name_en": "Poland", "name_zh": "波兰",
        "fifa_ranking": 22, "elo": 1820, "confederation": "UEFA",
        "coach": "Czesław Michniewicz", "coach_zh": "切斯瓦夫·米赫涅维奇",
        "captain": "Robert Lewandowski", "captain_zh": "罗伯特·莱万多夫斯基",
        "home_kit_color": "#FFFFFF",
    },
    "RUS": {
        "name_en": "Russia", "name_zh": "俄罗斯",
        "fifa_ranking": 38, "elo": 1700, "confederation": "UEFA",
        "coach": "Valery Karpin", "coach_zh": "瓦列里·卡尔平",
        "captain": "Artem Dzyuba", "captain_zh": "阿尔乔姆·久巴",
        "home_kit_color": "#FFFFFF",
    },
    "SRB": {
        "name_en": "Serbia", "name_zh": "塞尔维亚",
        "fifa_ranking": 21, "elo": 1830, "confederation": "UEFA",
        "coach": "Dragan Stojković", "coach_zh": "德拉甘·斯托伊科维奇",
        "captain": "Dušan Tadić", "captain_zh": "杜桑·塔迪奇",
        "home_kit_color": "#C7363D",
    },
    "SWE": {
        "name_en": "Sweden", "name_zh": "瑞典",
        "fifa_ranking": 23, "elo": 1820, "confederation": "UEFA",
        "coach": "Janne Andersson", "coach_zh": "扬内·安德松",
        "captain": "Andreas Granqvist", "captain_zh": "安德烈亚斯·格兰奎斯特",
        "home_kit_color": "#FECC00",
    },
    "TUN": {
        "name_en": "Tunisia", "name_zh": "突尼斯",
        "fifa_ranking": 30, "elo": 1740, "confederation": "CAF",
        "coach": "Jalel Kadri", "coach_zh": "贾莱勒·卡德里",
        "captain": "Wahbi Khazri", "captain_zh": "瓦赫比·哈兹里",
        "home_kit_color": "#E70013",
    },
    "URU": {
        "name_en": "Uruguay", "name_zh": "乌拉圭",
        "fifa_ranking": 16, "elo": 1880, "confederation": "CONMEBOL",
        "coach": "Diego Alonso", "coach_zh": "迭戈·阿隆索",
        "captain": "Diego Godín", "captain_zh": "迭戈·戈丁",
        "home_kit_color": "#7ECEEE",
    },
    "WAL": {
        "name_en": "Wales", "name_zh": "威尔士",
        "fifa_ranking": 19, "elo": 1830, "confederation": "UEFA",
        "coach": "Rob Page", "coach_zh": "罗布·佩奇",
        "captain": "Gareth Bale", "captain_zh": "加雷斯·贝尔",
        "home_kit_color": "#FFFFFF",
    },
}


def main() -> None:
    teams_path = config.teams_json
    with open(teams_path, encoding="utf-8") as f:
        existing = json.load(f)

    # Find teams in warehouse that are not yet seeded
    repo = MatchRepository()
    warehouse_teams: set[str] = set()
    from src.data.db import get_connection
    with get_connection() as conn:
        for row in conn.execute("SELECT DISTINCT home_team_code FROM matches"):
            warehouse_teams.add(row[0])
        for row in conn.execute("SELECT DISTINCT away_team_code FROM matches"):
            warehouse_teams.add(row[0])

    missing = sorted(warehouse_teams - set(existing.keys()))
    added = 0
    for code in missing:
        if code in NEW_TEAM_SEEDS:
            existing[code] = NEW_TEAM_SEEDS[code]
            added += 1
            logger.info(f"  Added {code} ({NEW_TEAM_SEEDS[code]['name_zh']})")
        else:
            logger.warning(f"  No seed for {code}; add one to NEW_TEAM_SEEDS")

    with open(teams_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    logger.info(f"Added {added} team seeds. Total: {len(existing)} teams.")


if __name__ == "__main__":
    main()
