#!/usr/bin/env python3
"""Regenerate src/data/us_airports.csv from OurAirports (public domain).

Keeps U.S. (incl. territories) large and medium airports with scheduled
passenger service, i.e. regional and international airports, not private
strips, heliports or military fields.

Usage: python scripts/update_airports.py
"""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import requests

SOURCE_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
OUT = Path(__file__).resolve().parents[1] / "src" / "data" / "us_airports.csv"
COUNTRIES = {"US", "PR", "GU", "VI", "AS", "MP"}
TYPES = {"large_airport", "medium_airport"}
FIELDS = ["ident", "iata_code", "name", "type", "municipality", "iso_region",
          "latitude_deg", "longitude_deg", "home_link"]


def main() -> int:
    response = requests.get(SOURCE_URL, timeout=120)
    response.raise_for_status()
    rows = [
        {k: r[k] for k in FIELDS}
        for r in csv.DictReader(io.StringIO(response.text))
        if r["iso_country"] in COUNTRIES and r["type"] in TYPES and r["scheduled_service"] == "yes"
    ]
    if len(rows) < 300:  # sanity check against a truncated or changed upstream file
        print(f"error: only {len(rows)} airports matched; not overwriting {OUT}", file=sys.stderr)
        return 1
    rows.sort(key=lambda r: r["ident"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} airports to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
