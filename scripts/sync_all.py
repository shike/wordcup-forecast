"""Run all data synchronisation scripts in dependency order.

Usage:
    python -m scripts.sync_all            # run everything that's available
    python -m scripts.sync_all --no-photos  # skip the slow Wikipedia photo step

The default pipeline:

    1. StatsBomb Open Data   (match results + xG)
    2. Wikipedia squads page (32-team rosters, ages, clubs, wiki URLs)
    3. Wikipedia summaries   (player photos + Chinese names)
    4. FIFA rankings CSV     (when operator drops data/fifa_ranking.csv)
    5. ELO snapshot          (bundled 2022 reference values)

The Wikipedia step (2) is the highest-leverage one because it brings in
32 * 26 = 832 real player records in a single HTTP call.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from loguru import logger


SCRIPTS = [
    "scripts.dedupe_warehouse",
    "scripts.expand_teams",
    "scripts.sync_wiki_squads",
    "scripts.sync_fifa_rankings",
]


def run_module(name: str, extra_args: list[str]) -> int:
    logger.info(f"=== Running {name} ===")
    result = subprocess.run(
        [sys.executable, "-m", name, *extra_args],
        capture_output=True, text=True,
    )
    if result.stdout:
        for line in result.stdout.splitlines()[-5:]:
            logger.info(f"  {line}")
    if result.returncode != 0:
        logger.error(f"{name} FAILED (exit {result.returncode}):")
        for line in result.stderr.splitlines()[-10:]:
            logger.error(f"  {line}")
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-photos", action="store_true",
                        help="Skip Wikipedia photo downloads (saves time)")
    args, _unknown = parser.parse_known_args()

    extra = ["--no-photos"] if args.no_photos else []
    overall = 0
    for name in SCRIPTS:
        rc = run_module(name, extra)
        overall = overall or rc

    if overall == 0:
        logger.success("All sync steps completed.")
    else:
        logger.error(f"Sync completed with errors (exit {overall}).")
    sys.exit(overall)


if __name__ == "__main__":
    main()
