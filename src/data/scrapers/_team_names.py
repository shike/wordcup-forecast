"""Team name resolution for external datasets.

Maps free-text team names (e.g. from martj42/international_results CSV) to the
project's stable 3-letter codes, taking into account historical country name
changes and split/merged federations.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path


# Direct mapping from CSV names to project codes for current country names.
# Kept explicit so every mapping is auditable.
MARTJ42_TO_CODE: dict[str, str] = {
    "Argentina": "ARG",
    "Australia": "AUS",
    "Belgium": "BEL",
    "Bosnia and Herzegovina": "BIH",
    "Brazil": "BRA",
    "Cameroon": "CMR",
    "Canada": "CAN",
    "Cape Verde": "CPV",
    "Colombia": "COL",
    "Costa Rica": "CRC",
    "Croatia": "CRO",
    "Denmark": "DEN",
    "Ecuador": "ECU",
    "Egypt": "EGY",
    "England": "ENG",
    "France": "FRA",
    "Germany": "GER",
    "Ghana": "GHA",
    "Haiti": "HAI",
    "Iran": "IRN",
    "Iceland": "ISL",
    "Italy": "ITA",
    "Japan": "JPN",
    "Mexico": "MEX",
    "Morocco": "MAR",
    "Netherlands": "NED",
    "Nigeria": "NGA",
    "Panama": "PAN",
    "Paraguay": "PAR",
    "Peru": "PER",
    "Poland": "POL",
    "Portugal": "POR",
    "Qatar": "QAT",
    "Russia": "RUS",
    "Saudi Arabia": "KSA",
    "Scotland": "SCO",
    "Senegal": "SEN",
    "Serbia": "SRB",
    "South Korea": "KOR",
    "Spain": "ESP",
    "Sweden": "SWE",
    "Switzerland": "SUI",
    "Tunisia": "TUN",
    "Turkey": "TUR",
    "United States": "USA",
    "Uruguay": "URU",
    "Wales": "WAL",
}


# Historical aliases that resolve to a project code only within a date range.
# Each tuple: (csv_name, project_code, start_date, end_date)
HISTORICAL_ALIASES: list[tuple[str, str, date, date]] = [
    ("Soviet Union", "RUS", date(1940, 1, 1), date(1991, 12, 31)),
    ("CIS", "RUS", date(1992, 1, 1), date(1992, 12, 31)),
    ("FR Yugoslavia", "SRB", date(1994, 12, 23), date(2003, 2, 3)),
    ("Serbia and Montenegro", "SRB", date(2003, 2, 4), date(2006, 6, 21)),
    ("West Germany", "GER", date(1949, 1, 1), date(1990, 10, 2)),
    ("German DR", "GER", date(1949, 1, 1), date(1990, 10, 2)),
    ("Czechoslovakia", "CZE", date(1918, 1, 1), date(1992, 12, 31)),
]


# Date-independent aliases that map a CSV name to a project code.
ADDITIONAL_ALIASES: dict[str, str] = {
    "Bosnia-Herzegovina": "BIH",
    "Türkiye": "TUR",
    "USA": "USA",
    "United States of America": "USA",
    "Korea Republic": "KOR",
    "Republic of Ireland": "IRL",  # not in project, kept for completeness
    "Czech Republic": "CZE",  # not in project
}


def resolve_team_name(name: str, match_date: str | None = None) -> str | None:
    """Resolve a CSV team name to a project 3-letter code.

    Args:
        name: Team name as it appears in the external dataset.
        match_date: ISO date string used for historical alias resolution.

    Returns None if the name cannot be mapped to a project code.
    """
    name = name.strip()
    if name in MARTJ42_TO_CODE:
        return MARTJ42_TO_CODE[name]
    if name in ADDITIONAL_ALIASES:
        return ADDITIONAL_ALIASES[name]

    if match_date:
        try:
            d = date.fromisoformat(match_date)
        except ValueError:
            d = None
        if d:
            for alias, code, start, end in HISTORICAL_ALIASES:
                if name == alias and start <= d <= end:
                    return code
    return None


def load_project_mapping(path: Path | None = None) -> dict[str, str]:
    """Load the optional user-editable JSON mapping file.

    Returns a name->code dict merged on top of the built-in mapping.
    """
    if path is None:
        path = Path(__file__).parents[3] / "data" / "team_name_mapping.json"
    mapping: dict[str, str] = {}
    if path.exists():
        mapping.update(json.loads(path.read_text(encoding="utf-8")))
    mapping.update(MARTJ42_TO_CODE)
    mapping.update(ADDITIONAL_ALIASES)
    return mapping
