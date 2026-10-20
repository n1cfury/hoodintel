"""Closest regional or international airport, from a bundled OurAirports
snapshot (public domain). No network at report time.

Refresh the snapshot with: python scripts/update_airports.py
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from ..models import POIResult
from ..utils import haversine_miles

AIRPORTS_CSV = Path(__file__).resolve().parent.parent / "data" / "us_airports.csv"
AIRPORTS_SOURCE = "OurAirports (U.S. airports with scheduled passenger service)"
CATEGORY = "Closest Regional/International Airport"
SIZE_LABELS = {"large_airport": "Large airport", "medium_airport": "Medium airport"}


@lru_cache(maxsize=1)
def load_airports() -> tuple[dict[str, str], ...]:
    with AIRPORTS_CSV.open(newline="", encoding="utf-8") as fh:
        return tuple(csv.DictReader(fh))


def closest_airport(lat: float, lon: float) -> POIResult | None:
    best: tuple[float, dict[str, str]] | None = None
    for row in load_airports():
        miles = haversine_miles(lat, lon, float(row["latitude_deg"]), float(row["longitude_deg"]))
        if best is None or miles < best[0]:
            best = (miles, row)
    if best is None:
        return None
    miles, row = best
    detail = " · ".join(
        part for part in [row["iata_code"], SIZE_LABELS.get(row["type"]), row["municipality"]] if part
    )
    return POIResult(
        category=CATEGORY,
        name=row["name"],
        latitude=float(row["latitude_deg"]),
        longitude=float(row["longitude_deg"]),
        distance_miles=round(miles, 2),
        osm_type="ourairports",
        osm_id=None,
        website=row.get("home_link") or None,
        detail=detail or None,
    )
