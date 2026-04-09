from __future__ import annotations

import requests

from ..config import AppConfig
from ..exceptions import NeighborhoodReportError
from ..models import GeocodeResult
from ..utils import extract_zip, safe_get

CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"


def geocode_address(
    session: requests.Session,
    address: str,
    config: AppConfig | None = None,
) -> GeocodeResult:
    config = config or AppConfig()
    params = {
        "address": address,
        "benchmark": "Public_AR_Current",
        "format": "json",
    }

    response = session.get(CENSUS_GEOCODER_URL, params=params, timeout=config.default_timeout)
    response.raise_for_status()
    data = response.json()

    matches = safe_get(data, "result", "addressMatches") or []
    if not matches:
        raise NeighborhoodReportError(f"No Census geocoder match found for: {address}")

    best = matches[0]
    matched_address = best.get("matchedAddress", address)
    coordinates = best.get("coordinates", {}) or {}
    lon = coordinates.get("x")
    lat = coordinates.get("y")
    if lat is None or lon is None:
        raise NeighborhoodReportError("Census geocoder returned a match without coordinates.")

    address_components = best.get("addressComponents", {}) or {}
    return GeocodeResult(
        input_address=address,
        matched_address=matched_address,
        latitude=float(lat),
        longitude=float(lon),
        zip_code=address_components.get("zip") or extract_zip(matched_address),
        city=address_components.get("city"),
        state=address_components.get("state"),
        county=address_components.get("county"),
    )
