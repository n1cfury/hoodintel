from __future__ import annotations

import requests

from ..config import AppConfig
from ..exceptions import NeighborhoodReportError
from ..http import throttle
from ..models import GeocodeResult
from ..utils import extract_zip, safe_get

CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
NOMINATIM_HOST = "nominatim.openstreetmap.org"
NOMINATIM_URL = f"https://{NOMINATIM_HOST}/search"
NOMINATIM_SOURCE = "OpenStreetMap Nominatim"


def geocode_address(
    session: requests.Session,
    address: str,
    config: AppConfig | None = None,
) -> GeocodeResult:
    """Census first (authoritative for U.S. addresses), then Nominatim for
    addresses Census TIGER doesn't have, such as many rural or new ones."""
    config = config or AppConfig()
    try:
        return geocode_census(session, address, config)
    except NeighborhoodReportError:
        result = geocode_nominatim(session, address, config)
        if result is None:
            raise NeighborhoodReportError(
                f"No geocoder match found for: {address}. Check the spelling, and include the city and state or ZIP."
            ) from None
        return result


def geocode_census(session: requests.Session, address: str, config: AppConfig) -> GeocodeResult:
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


def geocode_nominatim(session: requests.Session, address: str, config: AppConfig) -> GeocodeResult | None:
    """One request, within Nominatim's 1 req/s usage policy."""
    params = {"q": address, "format": "jsonv2", "addressdetails": 1, "countrycodes": "us", "limit": 1}
    throttle(NOMINATIM_HOST)
    response = session.get(NOMINATIM_URL, params=params, timeout=config.default_timeout)
    response.raise_for_status()
    results = response.json()
    if not results:
        return None
    best = results[0]
    parts = best.get("address", {}) or {}
    state_code = str(parts.get("ISO3166-2-lvl4", "")).removeprefix("US-") or None
    return GeocodeResult(
        input_address=address,
        matched_address=best.get("display_name", address),
        latitude=float(best["lat"]),
        longitude=float(best["lon"]),
        zip_code=extract_zip(parts.get("postcode")),
        city=parts.get("city") or parts.get("town") or parts.get("village") or parts.get("hamlet"),
        state=state_code or parts.get("state"),
        county=parts.get("county"),
        source=NOMINATIM_SOURCE,
        precision=None if parts.get("house_number") else f"approximate ({best.get('addresstype') or 'area'} level)",
    )
