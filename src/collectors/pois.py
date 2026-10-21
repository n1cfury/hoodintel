from __future__ import annotations

import math
import re
import time
from typing import Any, Callable

import requests

from ..collectors.geocode import NOMINATIM_HOST, NOMINATIM_URL
from ..config import AppConfig
from ..http import throttle
from ..models import POIResult
from ..utils import haversine_miles

# Overpass asks clients to back off on these instead of hammering it.
RETRY_STATUSES = {429, 502, 503, 504}
OVERPASS_CLIENT_TIMEOUT = 45
OVERPASS_BACKOFF_SECONDS = [3, 8]

TagMatcher = Callable[[dict[str, Any]], bool]


# Nominatim returns at most this many results per search, ranked by
# importance rather than distance; boxes start small so that cap rarely bites.
NOMINATIM_LIMIT = 40
NOMINATIM_BOX_HALF_WIDTHS_M = [2000, 8000, 25000]


class POICategory:
    """How to find one kind of POI: a Nominatim search, Overpass selectors,
    and the same filter in Python, so combined results can be split back
    into categories locally."""

    def __init__(self, label: str, nominatim_query: str, selectors: list[str], matches: TagMatcher):
        self.label = label
        self.nominatim_query = nominatim_query
        self.selectors = selectors
        self.matches = matches


_URGENT = re.compile(r"urgent", re.IGNORECASE)
_CLINIC_TYPES = ("clinic", "doctors", "doctor", "healthcare", "hospital")


def _is_urgent_care(tags: dict[str, Any]) -> bool:
    clinic = tags.get("amenity") in _CLINIC_TYPES or tags.get("healthcare") in _CLINIC_TYPES
    return clinic and bool(_URGENT.search(str(tags.get("name", ""))))


POI_CATEGORIES = [
    POICategory("Closest Gas Station", "[amenity=fuel]", ["[amenity=fuel]"], lambda t: t.get("amenity") == "fuel"),
    POICategory(
        "Closest Hospital",
        "[amenity=hospital]",
        ["[amenity=hospital]", "[healthcare=hospital]"],
        lambda t: t.get("amenity") == "hospital" or t.get("healthcare") == "hospital",
    ),
    POICategory(
        "Closest Urgent Care",
        "urgent care",
        ['[amenity~"^(clinic|doctors)$"][name~"urgent",i]', '[healthcare~"^(clinic|doctor)$"][name~"urgent",i]'],
        _is_urgent_care,
    ),
    POICategory(
        "Closest Veterinary Clinic", "[amenity=veterinary]", ["[amenity=veterinary]"], lambda t: t.get("amenity") == "veterinary"
    ),
    POICategory(
        "Closest Fire Station", "[amenity=fire_station]", ["[amenity=fire_station]"], lambda t: t.get("amenity") == "fire_station"
    ),
    # Nominatim doesn't index shop=grocery as a searchable type, so it finds
    # supermarkets only; the Overpass fallback also accepts smaller grocers.
    POICategory(
        "Closest Grocery Store",
        "[shop=supermarket]",
        ["[shop=supermarket]", "[shop=grocery]"],
        lambda t: t.get("shop") in ("supermarket", "grocery"),
    ),
    POICategory("Closest School", "[amenity=school]", ["[amenity=school]"], lambda t: t.get("amenity") == "school"),
]


def _describe(tags: dict[str, Any]) -> str | None:
    """Short extra line for categories where the kind matters (schools)."""
    if tags.get("amenity") != "school":
        return None
    parts = [str(tags["operator:type"]).capitalize() if tags.get("operator:type") else None,
             f"grades {tags['grades']}" if tags.get("grades") else None]
    return " · ".join(p for p in parts if p) or None


def build_overpass_query(lat: float, lon: float, radius_m: int, selectors: list[str]) -> str:
    blocks = " ".join(f"nwr(around:{radius_m},{lat},{lon}){selector};" for selector in selectors)
    return f"[out:json][timeout:25];({blocks});out center tags;"


def normalize_osm_element(element: dict[str, Any]) -> tuple[float, float] | None:
    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center")
    if isinstance(center, dict) and "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None


def build_osm_address(tags: dict[str, Any]) -> str | None:
    line1 = " ".join(part for part in [tags.get("addr:housenumber"), tags.get("addr:street")] if part)
    parts = [part for part in [line1, tags.get("addr:city"), tags.get("addr:state"), tags.get("addr:postcode")] if part]
    if parts:
        return ", ".join(parts)
    if tags.get("addr:full"):
        return str(tags["addr:full"])
    return None


def run_overpass(session: requests.Session, query: str, config: AppConfig) -> list[dict[str, Any]]:
    """POST a query, failing over between endpoints right away and backing
    off before each later round, as Overpass asks busy clients to do."""
    endpoints = config.overpass_endpoints
    rounds = len(OVERPASS_BACKOFF_SECONDS) + 1
    last_exception: requests.RequestException | None = None
    for round_no in range(rounds):
        if round_no:
            time.sleep(OVERPASS_BACKOFF_SECONDS[round_no - 1])
        for endpoint in endpoints:
            try:
                response = session.post(endpoint, data={"data": query}, timeout=OVERPASS_CLIENT_TIMEOUT)
                response.raise_for_status()
                return response.json().get("elements", []) or []
            except requests.RequestException as exc:  # includes JSON decode errors
                status = exc.response.status_code if exc.response is not None else None
                if status is not None and status not in RETRY_STATUSES:
                    raise
                last_exception = exc
    assert last_exception is not None
    raise last_exception


def _to_poi(element: dict[str, Any], category: str, lat: float, lon: float) -> POIResult | None:
    point = normalize_osm_element(element)
    if not point:
        return None
    poi_lat, poi_lon = point
    tags = element.get("tags", {}) or {}
    kind = category.removeprefix("Closest ").lower()
    return POIResult(
        category=category,
        name=str(tags.get("name") or tags.get("brand") or tags.get("operator") or f"Unnamed {kind}"),
        latitude=poi_lat,
        longitude=poi_lon,
        distance_miles=round(haversine_miles(lat, lon, poi_lat, poi_lon), 2),
        osm_type=str(element.get("type", "unknown")),
        osm_id=element.get("id"),
        address=build_osm_address(tags),
        phone=tags.get("phone") or tags.get("contact:phone"),
        website=tags.get("website") or tags.get("contact:website"),
        raw_tags=tags,
        detail=_describe(tags),
    )


def _viewbox(lat: float, lon: float, half_width_m: int) -> str:
    dlat = half_width_m / 111_320
    dlon = half_width_m / (111_320 * max(math.cos(math.radians(lat)), 0.01))
    return f"{lon - dlon:.6f},{lat + dlat:.6f},{lon + dlon:.6f},{lat - dlat:.6f}"


def nominatim_closest(
    session: requests.Session, category: POICategory, lat: float, lon: float, config: AppConfig
) -> POIResult | None:
    """Search growing boxes around the point. A box's closest hit is only
    trusted when it's inside the box's inscribed circle and the result list
    wasn't truncated; otherwise the next, larger box is searched."""
    best: POIResult | None = None
    for half_width in NOMINATIM_BOX_HALF_WIDTHS_M:
        params = {
            "q": category.nominatim_query,
            "format": "jsonv2",
            "limit": NOMINATIM_LIMIT,
            "bounded": 1,
            "viewbox": _viewbox(lat, lon, half_width),
            "extratags": 1,
            "addressdetails": 1,
        }
        throttle(NOMINATIM_HOST)
        response = session.get(NOMINATIM_URL, params=params, timeout=config.default_timeout)
        response.raise_for_status()
        results = response.json()
        candidates = []
        for item in results:
            tags = {**(item.get("extratags") or {}), item.get("category", ""): item.get("type"), "name": item.get("name")}
            tags.update(_nominatim_address_tags(item.get("address") or {}))
            if not category.matches(tags):
                continue
            element = {"type": item.get("osm_type"), "id": item.get("osm_id"), "lat": item["lat"], "lon": item["lon"], "tags": tags}
            if poi := _to_poi(element, category.label, lat, lon):
                candidates.append(poi)
        if candidates:
            best = min(candidates, key=lambda item: item.distance_miles)
            within = best.distance_miles * 1609.344 <= half_width
            if within and len(results) < NOMINATIM_LIMIT:
                return best
    return best


def _nominatim_address_tags(address: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in {
            "addr:housenumber": address.get("house_number"),
            "addr:street": address.get("road"),
            "addr:city": address.get("city") or address.get("town") or address.get("village"),
            "addr:state": str(address.get("ISO3166-2-lvl4", "")).removeprefix("US-") or None,
            "addr:postcode": address.get("postcode"),
        }.items()
        if v
    }


def query_overpass_closest_all(
    session: requests.Session,
    *,
    lat: float,
    lon: float,
    categories: list[POICategory],
    config: AppConfig,
) -> tuple[dict[str, POIResult | None], list[str]]:
    """Closest POI per category, plus error messages. One combined query per
    radius; wider radii are only queried for categories still missing."""
    found: dict[str, POIResult | None] = {c.label: None for c in categories}
    errors: list[str] = []

    for radius in config.search_radii_meters:
        missing = [c for c in categories if found[c.label] is None]
        if not missing:
            break
        selectors = [s for c in missing for s in c.selectors]
        try:
            elements = run_overpass(session, build_overpass_query(lat, lon, radius, selectors), config)
        except requests.RequestException as exc:
            errors.append(f"Overpass lookup within {radius // 1000} km failed: {exc}")
            break
        for category in missing:
            candidates = [
                poi
                for element in elements
                if category.matches(element.get("tags", {}) or {})
                and (poi := _to_poi(element, category.label, lat, lon))
            ]
            if candidates:
                found[category.label] = min(candidates, key=lambda item: item.distance_miles)
    return found, errors


def find_closest_pois(
    session: requests.Session,
    *,
    lat: float,
    lon: float,
    categories: list[POICategory] | None = None,
    config: AppConfig | None = None,
) -> tuple[dict[str, POIResult | None], list[str]]:
    """Nominatim first (fast, ~1 s per search); Overpass only for categories
    Nominatim failed on or found nothing for. Returns results and errors."""
    config = config or AppConfig()
    categories = categories or POI_CATEGORIES
    found: dict[str, POIResult | None] = {}
    errors: list[str] = []
    for category in categories:
        try:
            found[category.label] = nominatim_closest(session, category, lat, lon, config)
        except requests.RequestException as exc:
            errors.append(f"Nominatim search for {category.label.lower()} failed: {exc}")
            found[category.label] = None

    missing = [c for c in categories if found[c.label] is None]
    if missing:
        more, overpass_errors = query_overpass_closest_all(session, lat=lat, lon=lon, categories=missing, config=config)
        found.update({k: v for k, v in more.items() if v is not None})
        errors.extend(overpass_errors)
    return found, errors
