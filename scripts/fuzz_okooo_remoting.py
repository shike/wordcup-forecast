#!/usr/bin/env python3
"""Fuzz OKOOO Remoting/json.php class/method names.

OKOOO exposes an AMFPHP JSON-RPC gateway at:
    https://www.okooo.com/Remoting/json.php

Calling `json.php/ClassName.methodName/arg1/arg2` returns:
  - AMFPHP_FILE_NOT_FOUND        -> class does not exist
  - AMFPHP_INEXISTANT_METHOD     -> class exists, method does not
  - a JSON payload                -> the method exists and returned data

This script probes a starter wordlist. Use the results to build a real client,
then inspect the site's own JS with DevTools to find additional method names.
"""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from enum import Enum

import requests


GATEWAY = "https://www.okooo.com/Remoting/json.php"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.okooo.com/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


class ProbeResult(Enum):
    CLASS_MISSING = "CLASS_MISSING"
    METHOD_MISSING = "METHOD_MISSING"
    HIT = "HIT"
    ERROR = "ERROR"


@dataclass(frozen=True)
class Probe:
    service: str
    method: str
    result: ProbeResult
    snippet: str


SERVICES = [
    "Schedule",
    "Match",
    "Odds",
    "Live",
    "Score",
    "Team",
    "League",
    "User",
    "Jingcai",
    "Beidan",
    "Lottery",
    "Game",
    "Football",
    "Soccer",
    "Data",
    "Index",
]

METHODS = [
    "getList",
    "getById",
    "getByDate",
    "getByMatchId",
    "getSchedule",
    "getMatch",
    "getMatches",
    "getOdds",
    "getLive",
    "getScore",
    "getDetail",
    "getInfo",
    "getData",
    "getRank",
    "getStanding",
    "getHistory",
    "getRecent",
    "getInviteLink",
]


def probe(service: str, method: str, delay: float = 0.2) -> Probe:
    url = f"{GATEWAY}/{service}.{method}/"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        text = resp.text
    except requests.RequestException as exc:
        return Probe(service, method, ProbeResult.ERROR, str(exc)[:80])

    if "aliyun_waf" in text.lower() or "Blocked" in text or resp.status_code != 200:
        return Probe(service, method, ProbeResult.ERROR, "WAF/block")
    if "AMFPHP_FILE_NOT_FOUND" in text:
        return Probe(service, method, ProbeResult.CLASS_MISSING, "")
    if "AMFPHP_INEXISTANT_METHOD" in text:
        return Probe(service, method, ProbeResult.METHOD_MISSING, "")

    # Method exists (may be an auth/param error, but class+method are real).
    snippet = text[:120].replace("\n", " ")
    return Probe(service, method, ProbeResult.HIT, snippet)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fuzz OKOOO Remoting methods")
    parser.add_argument(
        "--services",
        default=None,
        help="Comma-separated service names to probe (default: built-in list)",
    )
    parser.add_argument(
        "--methods",
        default=None,
        help="Comma-separated method names to probe (default: built-in list)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds between requests (default: 1.0). Increase if you hit WAF.",
    )
    args = parser.parse_args()

    services = args.services.split(",") if args.services else SERVICES
    methods = args.methods.split(",") if args.methods else METHODS

    hits: list[Probe] = []
    existing_services: set[str] = set()

    print(f"Probing {len(services)} services × {len(methods)} methods...")
    blocked = False
    for service in services:
        if blocked:
            break
        service_has_class = False
        for method in methods:
            p = probe(service, method, delay=args.delay)
            if p.result == ProbeResult.ERROR and "WAF" in p.snippet:
                print(f"\nWAF/rate-limit hit at {service}.{method}. Stopping.")
                print("Wait a few minutes, increase --delay, or use a proxy.")
                blocked = True
                break
            if p.result in (ProbeResult.HIT, ProbeResult.METHOD_MISSING):
                service_has_class = True
                existing_services.add(service)
            if p.result == ProbeResult.HIT:
                hits.append(p)
                print(f"  HIT  {service}.{method} -> {p.snippet}")
            time.sleep(args.delay)
        if service_has_class:
            print(f"  class exists: {service}Service")

    print("\n--- Summary ---")
    print(f"Services with existing classes: {sorted(existing_services)}")
    if hits:
        print("Working methods:")
        for h in hits:
            print(f"  {h.service}.{h.method}")
    else:
        print("No working methods found with this wordlist.")
        print(
            "Tip: open https://www.okooo.com/soccer/ in DevTools, "
            "filter Network for 'Remoting/json.php', and add the real method names."
        )


if __name__ == "__main__":
    main()
