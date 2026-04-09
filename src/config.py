from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ============================================================
# API KEYS / OPTIONAL SOURCE CONFIG
# Keep your keys here for local use, or better: export them as
# environment variables and let this block read them automatically.
#
# Recommended free / low-friction sources:
# - CENSUS_API_KEY       -> U.S. Census Data API (ACS demographics/housing)
# - AIRNOW_API_KEY       -> EPA AirNow AQI / smoke / forecast data
# - FCC_BDC_API_KEY      -> FCC Broadband Data Collection public API access
#
# Recommended paid sources:
# - CRIMEOMETER_API_KEY  -> crime incidents / crime stats / 911 data
# - WALKSCORE_API_KEY    -> walk / bike / transit scores
# - ATTOM_API_KEY        -> parcel / assessor / property datasets
# - GOOGLE_MAPS_API_KEY  -> geocoding / places / nearby search
# - MAPBOX_ACCESS_TOKEN  -> geocoding / map rendering / search
# - LOCATIONIQ_API_KEY   -> low-cost geocoding / POI / map services
# - SPOKEO_API_KEY       -> optional people/address enrichment if available
# ============================================================
API_KEYS = {
    # Free / public-ish
    "CENSUS_API_KEY": os.getenv("CENSUS_API_KEY", ""),
    "AIRNOW_API_KEY": os.getenv("AIRNOW_API_KEY", ""),
    "FCC_BDC_API_KEY": os.getenv("FCC_BDC_API_KEY", ""),
    # Paid / commercial
    "CRIMEOMETER_API_KEY": os.getenv("CRIMEOMETER_API_KEY", ""),
    "WALKSCORE_API_KEY": os.getenv("WALKSCORE_API_KEY", ""),
    "ATTOM_API_KEY": os.getenv("ATTOM_API_KEY", ""),
    "GOOGLE_MAPS_API_KEY": os.getenv("GOOGLE_MAPS_API_KEY", ""),
    "MAPBOX_ACCESS_TOKEN": os.getenv("MAPBOX_ACCESS_TOKEN", ""),
    "LOCATIONIQ_API_KEY": os.getenv("LOCATIONIQ_API_KEY", ""),
    "SPOKEO_API_KEY": os.getenv("SPOKEO_API_KEY", ""),
}

OPTIONAL_API_ENDPOINTS = {
    "AIRNOW_BASE_URL": "https://www.airnowapi.org/aq/observation/latLong/current/",
    "FCC_BDC_BASE_URL": "https://broadbandmap.fcc.gov/api/public/",
    "CRIMEOMETER_BASE_URL": "https://api.crimeometer.com/v2/",
    "WALKSCORE_BASE_URL": "https://api.walkscore.com/score",
    "ATTOM_BASE_URL": "https://api.gateway.attomdata.com/propertyapi/v1.0.0/",
    "GOOGLE_GEOCODE_BASE_URL": "https://maps.googleapis.com/maps/api/geocode/json",
    "MAPBOX_GEOCODE_BASE_URL": "https://api.mapbox.com/search/geocode/v6/forward",
    "LOCATIONIQ_SEARCH_BASE_URL": "https://us1.locationiq.com/v1/search",
}

POI_QUERIES = {
    "Closest Gas Station": ["[amenity=fuel]"],
    "Closest Hospital": ["[amenity=hospital]", "[healthcare=hospital]"],
    "Closest Urgent Care": [
        '[amenity=clinic][name~"(?i)urgent"]',
        '[healthcare=clinic][name~"(?i)urgent"]',
        '[name~"(?i)urgent care"]',
    ],
    "Closest Veterinary Clinic": ["[amenity=veterinary]"],
}

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

USER_AGENT = "HoodIntel/1.0 (public-osint local tool)"
DEFAULT_TIMEOUT = 30
DEFAULT_ACS_YEAR = 2023
DEFAULT_SEARCH_RADII_METERS = [5000, 10000, 20000]
DEFAULT_OUTPUT_BASENAME = "neighborhood_report"


@dataclass(slots=True)
class AppConfig:
    default_timeout: int = DEFAULT_TIMEOUT
    acs_year: int = DEFAULT_ACS_YEAR
    search_radii_meters: list[int] = field(
        default_factory=lambda: list(DEFAULT_SEARCH_RADII_METERS)
    )
    user_agent: str = USER_AGENT
    overpass_endpoints: list[str] = field(default_factory=lambda: list(OVERPASS_ENDPOINTS))
    default_output_basename: str = DEFAULT_OUTPUT_BASENAME


@dataclass(slots=True)
class ReportOptions:
    debug: bool = False
    include_debug_snapshot: bool = False
    acs_year: int = DEFAULT_ACS_YEAR
    output_path: Path | None = None
    json_output_path: Path | None = None


def has_api_key(name: str) -> bool:
    return bool(API_KEYS.get(name, "").strip())
