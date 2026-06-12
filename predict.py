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
        description="World Cup match prediction with full PPT report",
    )
    parser.add_argument("--team-a", help="Team A name (English or Chinese) or code (e.g. BRA)")
    parser.add_argument("--team-b", help="Team B name (English or Chinese) or code (e.g. ARG)")
    parser.add_argument(
        "--match-date", default=datetime.now().strftime("%Y-%m-%d"), help="Match date YYYY-MM-DD"
    )
    parser.add_argument(
        "--stage",
        default="group",
        choices=["group", "round_of_16", "quarterfinal", "semifinal", "final", "third_place"],
    )
    parser.add_argument("--venue", default="TBD", help="Stadium / venue")
    parser.add_argument(
        "--lang", default=config.default_lang, choices=["zh", "en", "bilingual"]
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Compute prediction but skip PPT generation"
    )
    parser.add_argument("--output", help="Output PPTX path")
    parser.add_argument("--simulations", type=int, default=10_000, help="Monte Carlo sim count")
    parser.add_argument("--list-teams", action="store_true", help="List known teams and exit")
    parser.add_argument(
        "--fetch-fixtures",
        nargs="?",
        const="today",
        default=None,
        metavar="DATE",
        help="Fetch and list soccer fixtures for DATE (YYYY-MM-DD) or 'today' (default: today). "
             "Add --all to see every match.",
    )
    parser.add_argument(
        "--all-fixtures",
        action="store_true",
        help="When using --fetch-fixtures, show all matches (not just top leagues).",
    )
    parser.add_argument(
        "--predict-fixture",
        type=int,
        metavar="N",
        help="Predict the Nth fixture from a previous --fetch-fixtures call. "
             "Uses the cached fixture list (most recent fetch).",
    )
    parser.add_argument(
        "--fixture-date",
        default=None,
        help="Date for --predict-fixture in YYYY-MM-DD (default: last fetched).",
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


def _resolve_fixture_team(name: str):
    """Map a fixture team name to our Team model via fuzzy match."""
    teams = search_team(name)
    if teams:
        return teams[0]
    # try by country code or partial match
    for code, t in [(__import__("json").load(open(config.teams_json)).get(k, {}).get("code", k), v)
                    for k, v in __import__("json").load(open(config.teams_json)).items()]:
        if name.lower() in t["name_en"].lower() or name in t.get("name_zh", ""):
            from src.utils.models import Team
            return Team(code=code, **t)
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
        from src.data.fixtures import fetch_fixtures, filter_interesting
        date_arg = None if args.fetch_fixtures == "today" else args.fetch_fixtures
        fx = fetch_fixtures(date_arg)
        if not args.all_fixtures:
            fx = filter_interesting(fx)
        print(f"\n{len(fx)} matches")
        print("-" * 80)
        for i, f in enumerate(fx, 1):
            print(f"  [{i}] {f.short()}")
            if f.venue:
                print(f"        venue: {f.venue}  ·  status: {f.status}")
        if fx:
            print(f"\nTo predict match N, use: --predict-fixture N --fixture-date {date_arg or 'today'}")
        return

    if args.predict_fixture is not None:
        from src.data.fixtures import fetch_fixtures, filter_interesting
        fx = fetch_fixtures(args.fixture_date)
        if not args.all_fixtures:
            fx = filter_interesting(fx)
        if args.predict_fixture < 1 or args.predict_fixture > len(fx):
            logger.error(f"Invalid fixture index {args.predict_fixture}. 1..{len(fx)} available.")
            sys.exit(1)
        chosen = fx[args.predict_fixture - 1]
        logger.info(f"Predicting fixture #{args.predict_fixture}: {chosen.home_team} vs {chosen.away_team}")
        team_a = _resolve_fixture_team(chosen.home_team)
        team_b = _resolve_fixture_team(chosen.away_team)
        if team_a is None or team_b is None:
            logger.error(
                f"Teams not in seed database: {chosen.home_team} / {chosen.away_team}.\n"
                f"Add entries to data/teams.json and data/squads/ if you want to predict this match."
            )
            sys.exit(1)
        from src.pipeline import run_prediction
        result = run_prediction(
            team_a=team_a, team_b=team_b,
            match_date=(chosen.kickoff_utc or "")[:10] or datetime.now().strftime("%Y-%m-%d"),
            stage="group", venue=chosen.venue or "TBD",
            lang=args.lang, simulations=args.simulations,
        )
        if args.dry_run:
            print(f"Win A: {result.model_probs.consensus[0]:.1%}")
            print(f"Draw : {result.model_probs.consensus[1]:.1%}")
            print(f"Win B: {result.model_probs.consensus[2]:.1%}")
            return
        from src.ppt.builder import build_ppt
        output_path = Path(args.output) if args.output else None
        ppt_path = build_ppt(result, lang=args.lang, output_path=output_path)
        logger.success(f"PPT written: {ppt_path}")
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
        print(f"Win A: {result.model_probs.consensus[0]:.1%}")
        print(f"Draw : {result.model_probs.consensus[1]:.1%}")
        print(f"Win B: {result.model_probs.consensus[2]:.1%}")
        return

    from src.ppt.builder import build_ppt

    output_path = Path(args.output) if args.output else None
    ppt_path = build_ppt(result, lang=args.lang, output_path=output_path)
    logger.success(f"PPT written: {ppt_path}")


if __name__ == "__main__":
    main()
