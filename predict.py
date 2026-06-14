"""CLI entry point for World Cup prediction."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.data.team_data import get_team, search_team
from src.utils.config import config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="wordcup-forecast",
        description="世界杯比赛预测 · 完整 PPT 报告生成器",
    )
    parser.add_argument("--team-a", help="主队名称（中文 / 英文 / 三字代码，如 BRA）")
    parser.add_argument("--team-b", help="客队名称（中文 / 英文 / 三字代码，如 ARG）")
    parser.add_argument(
        "--match-date", default=datetime.now().strftime("%Y-%m-%d"), help="比赛日期 YYYY-MM-DD"
    )
    parser.add_argument(
        "--stage",
        default="group",
        choices=["group", "round_of_16", "quarterfinal", "semifinal", "final", "third_place"],
    )
    parser.add_argument("--venue", default="TBD", help="比赛场地")
    parser.add_argument(
        "--lang", default=config.default_lang, choices=["zh", "en", "bilingual"],
        help="PPT 语言：zh 中文 / en 英文 / bilingual 中英双语"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="只计算预测，不生成 PPT"
    )
    parser.add_argument("--output", help="PPT 输出路径（可选）")
    parser.add_argument("--simulations", type=int, default=10_000, help="蒙特卡洛模拟次数")
    parser.add_argument("--list-teams", action="store_true", help="列出已知球队并退出")
    parser.add_argument(
        "--fetch-fixtures",
        nargs="?",
        const="today",
        default=None,
        metavar="日期",
        help="拉取指定日期的足球赛程（YYYY-MM-DD 或 today），并显示列表"
    )
    parser.add_argument(
        "--all-fixtures",
        action="store_true",
        help="配合 --fetch-fixtures，显示所有比赛（不仅顶级联赛）"
    )
    parser.add_argument(
        "--predict-fixture",
        type=int,
        metavar="N",
        help="预测赛程列表中第 N 场比赛（先用 --fetch-fixtures 拉取）"
    )
    parser.add_argument(
        "--fixture-date",
        default=None,
        help="配合 --predict-fixture，指定赛程日期 YYYY-MM-DD"
    )
    return parser.parse_args()


def resolve_team(query: str):
    """Resolve a free-form team query to a Team object."""
    query = query.strip()
    teams = search_team(query)
    if not teams:
        upper = query.upper()
        try:
            return get_team(upper)
        except KeyError:
            logger.error(f"Team not found: {query}")
            sys.exit(1)
    if len(teams) == 1:
        return teams[0]
    # exact match preference
    for t in teams:
        if t.name_en.lower() == query.lower() or t.name_zh == query:
            return t
    return teams[0]


def _resolve_fixture_team(name: str, code: str | None = None):
    """Map a fixture team name to our Team model via fuzzy match + aliases.

    `code` is the 3-letter ESPN abbreviation (e.g. "USA") which gives a
    fast exact lookup before any fuzzy matching.
    """
    raw = __import__("json").load(open(config.teams_json))
    if code and code.upper() in raw:
        from src.utils.models import Team
        return Team(code=code.upper(), **raw[code.upper()])
    teams = search_team(name)
    if teams:
        return teams[0]
    for code_k, t in raw.items():
        if name.lower() in t.get("name_en", "").lower() or name in t.get("name_zh", ""):
            from src.utils.models import Team
            return Team(code=code_k, **t)
    return None


def main() -> None:
    args = parse_args()

    if args.list_teams:
        teams = sorted(
            (get_team(c) for c in __import__("json").load(open(config.teams_json))),
            key=lambda t: t.fifa_ranking,
        )
        for t in teams:
            print(f"{t.code}  {t.name_zh:8s} / {t.name_en:14s}  FIFA #{t.fifa_ranking}")
        return

    if args.fetch_fixtures is not None:
        from src.data.fixtures import (
            TIMEZONE_LABEL,
            fetch_fixtures,
            filter_interesting,
            to_beijing,
            venue_chinese,
        )
        date_arg = None if args.fetch_fixtures == "today" else args.fetch_fixtures
        fx = fetch_fixtures(date_arg)
        if not args.all_fixtures:
            fx = filter_interesting(fx)
        print(f"\n{len(fx)} matches  ·  {TIMEZONE_LABEL}")
        print("-" * 80)
        for i, f in enumerate(fx, 1):
            print(f"  [{i}] {f.short()}")
            if f.venue:
                venue_zh = venue_chinese(f.venue)
                if venue_zh and venue_zh != f.venue:
                    print(f"        场地: {venue_zh}")
                    print(f"        Venue: {f.venue}")
                else:
                    print(f"        场地: {f.venue}")
                print(f"        状态: {f.status}")
        if fx:
            print(f"\n预测第 N 场: --predict-fixture N --fixture-date {date_arg or 'today'}")
        return

    if args.predict_fixture is not None:
        from src.data.fixtures import (
            fetch_fixtures,
            filter_interesting,
            to_beijing,
            venue_chinese,
        )
        fx = fetch_fixtures(args.fixture_date)
        if not args.all_fixtures:
            fx = filter_interesting(fx)
        if args.predict_fixture < 1 or args.predict_fixture > len(fx):
            logger.error(f"Invalid fixture index {args.predict_fixture}. 1..{len(fx)} available.")
            sys.exit(1)
        chosen = fx[args.predict_fixture - 1]
        logger.info(f"Predicting fixture #{args.predict_fixture}: {chosen.home_team} vs {chosen.away_team}")
        team_a = _resolve_fixture_team(chosen.home_team, code=chosen.home_code)
        team_b = _resolve_fixture_team(chosen.away_team, code=chosen.away_code)
        if team_a is None or team_b is None:
            logger.error(
                f"Teams not in seed database: {chosen.home_team} / {chosen.away_team}.\n"
                f"Add entries to data/teams.json and data/squads/ if you want to predict this match."
            )
            sys.exit(1)
        # PPT metadata in Beijing time
        bj = to_beijing(chosen.kickoff_utc)
        match_date = bj[:10] if bj else datetime.now().strftime("%Y-%m-%d")
        kickoff_cst = bj[11:] if bj else "TBD"
        venue_zh = venue_chinese(chosen.venue) or chosen.venue or "TBD"
        from src.pipeline import run_prediction
        result = run_prediction(
            team_a=team_a, team_b=team_b,
            match_date=match_date, stage="group", venue=venue_zh,
            lang=args.lang, simulations=args.simulations,
        )
        if args.dry_run:
            print(f"开球: {match_date} {kickoff_cst} (北京时间)  ·  场地: {venue_zh}")
            print(f"Win A: {result.model_probs.win_draw_loss[0]:.1%}")
            print(f"Draw : {result.model_probs.win_draw_loss[1]:.1%}")
            print(f"Win B: {result.model_probs.win_draw_loss[2]:.1%}")
            return
        from src.ppt.builder import build_ppt
        output_path = Path(args.output) if args.output else None
        ppt_path = build_ppt(result, lang=args.lang, output_path=output_path)
        logger.success(f"PPT 已生成：{ppt_path}")
        return

    if not args.team_a or not args.team_b:
        logger.error("Both --team-a and --team-b are required (or use --list-teams)")
        sys.exit(1)

    team_a = resolve_team(args.team_a)
    team_b = resolve_team(args.team_b)

    logger.info(f"Predicting: {team_a.name_zh} vs {team_b.name_zh}")
    logger.info(f"Date: {args.match_date}, Stage: {args.stage}")

    from src.pipeline import run_prediction

    result = run_prediction(
        team_a=team_a,
        team_b=team_b,
        match_date=args.match_date,
        stage=args.stage,
        venue=args.venue,
        lang=args.lang,
        simulations=args.simulations,
    )

    if args.dry_run:
        logger.info("Dry run — skipping PPT generation")
        print(f"Win A: {result.model_probs.win_draw_loss[0]:.1%}")
        print(f"Draw : {result.model_probs.win_draw_loss[1]:.1%}")
        print(f"Win B: {result.model_probs.win_draw_loss[2]:.1%}")
        return

    from src.ppt.builder import build_ppt

    output_path = Path(args.output) if args.output else None
    ppt_path = build_ppt(result, lang=args.lang, output_path=output_path)
    logger.success(f"PPT written: {ppt_path}")


if __name__ == "__main__":
    main()
