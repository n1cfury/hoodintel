from __future__ import annotations

from typing import Any

import requests

from ..config import AppConfig
from ..models import POIResult
from ..utils import haversine_miles


def build_overpass_query(lat: float, lon: float, radius_m: int, selectors: list[str]) -> str:
    blocks: list[str] = []
    for selector in selectors:
        blocks.extend(
            [
                f"node(around:{radius_m},{lat},{lon}){selector};",
                f"way(around:{radius_m},{lat},{lon}){selector};",
                f"relation(around:{radius_m},{lat},{lon}){selector};",
            ]
        )
    return f"""
    [out:json][timeout:25];
    (
      {' '.join(blocks)}
    );
    out center tags;
    """


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
    for fallback_key in ("addr:full", "name", "brand"):
        if tags.get(fallback_key):
            return str(tags[fallback_key])
    return None


def query_overpass_closest(
    session: requests.Session,
    *,
    lat: float,
    lon: float,
    category: str,
    selectors: list[str],
    config: AppConfig | None = None,
) -> POIResult | None:
    config = config or AppConfig()

    last_exception: Exception | None = None
    for endpoint in config.overpass_endpoints:
        for radius in config.search_radii_meters:
            try:
                query = build_overpass_query(lat, lon, radius, selectors)
                response = session.post(endpoint, data=query.encode("utf-8"), timeout=config.default_timeout)
                response.raise_for_status()
                elements = response.json().get("elements", []) or []
            except requests.RequestException as exc:
                last_exception = exc
                continue

            candidates: list[POIResult] = []
            for element in elements:
                point = normalize_osm_element(element)
                if not point:
                    continue
                poi_lat, poi_lon = point
                tags = element.get("tags", {}) or {}
                candidates.append(
                    POIResult(
                        category=category,
                        name=str(tags.get("name") or tags.get("brand") or tags.get("operator") or f"Unnamed {category}"),
                        latitude=poi_lat,
                        longitude=poi_lon,
                        distance_miles=round(haversine_miles(lat, lon, poi_lat, poi_lon), 2),
                        osm_type=str(element.get("type", "unknown")),
                        osm_id=element.get("id"),
                        address=build_osm_address(tags),
                        phone=tags.get("phone") or tags.get("contact:phone"),
                        website=tags.get("website") or tags.get("contact:website"),
                        raw_tags=tags,
                    )
                )
            if candidates:
                candidates.sort(key=lambda item: item.distance_miles)
                return candidates[0]
    if last_exception:
        raise last_exception
    return None
