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
