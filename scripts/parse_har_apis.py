#!/usr/bin/env python3
"""Extract API endpoints and query parameters from a Charles/Fiddler HAR file.

Usage:
    python scripts/parse_har_apis.py dongqiudi.har --domain dongqiudi
    python scripts/parse_har_apis.py hupu.har --domain hupu --method GET
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Any


def _extract_domain_patterns(url: str, domain_hint: str | None) -> str:
    """Return a normalised URL path with query keys but scrubbed values."""
    parsed = urllib.parse.urlparse(url)
    if domain_hint and domain_hint not in parsed.netloc:
        return ""
    query = urllib.parse.parse_qs(parsed.query)
    masked = {k: "..." for k in query}
    masked_query = urllib.parse.urlencode(masked, doseq=True)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{masked_query}".rstrip("?")


def parse_har(har_path: Path, domain_hint: str | None = None, method: str | None = None) -> dict[str, list[str]]:
    """Return a dict mapping endpoint patterns to example URLs."""
    data = json.loads(har_path.read_text(encoding="utf-8"))
    entries = data.get("log", {}).get("entries", [])

    endpoints: dict[str, list[str]] = defaultdict(list)

    for entry in entries:
        request = entry.get("request", {})
        url = request.get("url", "")
        req_method = request.get("method", "")

        if not url.startswith(("http://", "https://")):
            continue
        if method and req_method.upper() != method.upper():
            continue

        pattern = _extract_domain_patterns(url, domain_hint)
        if not pattern:
            continue
        endpoints[pattern].append(url)

    return dict(endpoints)


def _pretty_headers(request: dict[str, Any]) -> str:
    interesting = {"authorization", "x-auth", "token", "sign", "device-id", "user-agent"}
    headers = request.get("headers", [])
    out = []
    for h in headers:
        name = h.get("name", "").lower()
        if any(key in name for key in interesting):
            value = h.get("value", "")
            # Mask most of the value for safety.
            masked = value[:8] + "..." if len(value) > 12 else value
            out.append(f"    {name}: {masked}")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse API endpoints from a HAR file")
    parser.add_argument("har", type=Path, help="Path to .har file")
    parser.add_argument("--domain", default=None, help="Filter by domain substring")
    parser.add_argument("--method", default=None, help="Filter by HTTP method")
    parser.add_argument(
        "--examples",
        type=int,
        default=1,
        help="Number of example URLs to print per endpoint (default: 1)",
    )
    args = parser.parse_args()

    endpoints = parse_har(args.har, domain_hint=args.domain, method=args.method)
    if not endpoints:
        print("No matching endpoints found.")
        return

    print(f"Found {len(endpoints)} distinct endpoint patterns:\n")
    for pattern, examples in sorted(endpoints.items(), key=lambda kv: kv[0]):
        print(pattern)
        for url in examples[: args.examples]:
            print(f"  e.g. {url[:200]}")
        print()


if __name__ == "__main__":
    main()
