#!/usr/bin/env python3
"""
Neighborhood OSINT Report Generator

Usage:
    python hoodintel_v3.py "5452 Adobe Falls Rd #3, San Diego, CA 92120"

What it does:
- Geocodes a U.S. address using the U.S. Census Geocoder
- Looks up nearby public-map POIs using OpenStreetMap / Overpass
- Pulls ZIP/ZCTA housing metrics from Census ACS
- Writes a PDF report
- Optionally writes the raw results as JSON

Dependencies:
- requests
- reportlab
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


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

def has_api_key(name: str) -> bool:
    return bool(API_KEYS.get(name, "").strip())


USER_AGENT = "NeighborhoodOSINTReport/0.3 (public-osint local tool)"
DEFAULT_TIMEOUT = 30
DEFAULT_ACS_YEAR = 2023
DEFAULT_SEARCH_RADII_METERS = [5000, 10000, 20000]
DEFAULT_OUTPUT_BASENAME = "neighborhood_report"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


@dataclass
class GeocodeResult:
    input_address: str
    matched_address: str
    latitude: float
    longitude: float
    zip_code: str | None
    city: str | None
    state: str | None
    county: str | None = None


@dataclass
class POIResult:
    category: str
    name: str
    latitude: float
    longitude: float
    distance_miles: float
    osm_type: str
    osm_id: int | None
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    raw_tags: dict[str, Any] | None = None


class NeighborhoodReportError(Exception):
    """Custom exception for report generation errors."""


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
        }
    )
    return session


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_miles = 3958.7613
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return r_miles * c


def extract_zip(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"\b(\d{5})(?:-\d{4})?\b", text)
    return match.group(1) if match else None


def safe_get(d: dict[str, Any], *keys: str) -> Any:
    current: Any = d
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def slugify_address(address: str, max_len: int = 80) -> str:
    cleaned = address.lower().strip()
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return (cleaned[:max_len] or DEFAULT_OUTPUT_BASENAME)


def derive_default_output_path(address: str) -> Path:
    stem = slugify_address(address)
    return Path(f"{stem}.pdf")


def geocode_address(session: requests.Session, address: str) -> GeocodeResult:
    url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
    params = {
        "address": address,
        "benchmark": "Public_AR_Current",
        "format": "json",
    }

    resp = session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

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
    zip_code = address_components.get("zip") or extract_zip(matched_address)
    city = address_components.get("city")
    state = address_components.get("state")
    county = address_components.get("county")

    return GeocodeResult(
        input_address=address,
        matched_address=matched_address,
        latitude=float(lat),
        longitude=float(lon),
        zip_code=zip_code,
        city=city,
        state=state,
        county=county,
    )


def build_overpass_query(lat: float, lon: float, radius_m: int, selectors: list[str]) -> str:
    blocks = []
    for selector in selectors:
        blocks.append(f"node(around:{radius_m},{lat},{lon}){selector};")
        blocks.append(f"way(around:{radius_m},{lat},{lon}){selector};")
        blocks.append(f"relation(around:{radius_m},{lat},{lon}){selector};")

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
    parts = []
    house_num = tags.get("addr:housenumber")
    street = tags.get("addr:street")
    city = tags.get("addr:city")
    state = tags.get("addr:state")
    postcode = tags.get("addr:postcode")

    line1 = " ".join(p for p in [house_num, street] if p)
    if line1:
        parts.append(line1)
    if city:
        parts.append(city)
    if state:
        parts.append(state)
    if postcode:
        parts.append(postcode)

    if parts:
        return ", ".join(parts)

    for fallback_key in ("addr:full", "name", "brand"):
        if tags.get(fallback_key):
            return str(tags[fallback_key])

    return None


def _run_overpass_query(
    session: requests.Session,
    query: str,
    *,
    debug: bool = False,
) -> dict[str, Any]:
    last_error: Exception | None = None

    for endpoint in OVERPASS_ENDPOINTS:
        try:
            if debug:
                print(f"[*] Overpass query -> {urlparse(endpoint).netloc}")
            resp = session.post(endpoint, data=query.encode("utf-8"), timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_error = exc
            if debug:
                print(f"[!] Overpass failed at {endpoint}: {exc}", file=sys.stderr)
            time.sleep(0.5)

    if last_error:
        raise last_error
    raise NeighborhoodReportError("Overpass query failed without a specific exception.")


def query_overpass_closest(
    session: requests.Session,
    *,
    lat: float,
    lon: float,
    category: str,
    selectors: list[str],
    search_radii_m: list[int] | None = None,
    debug: bool = False,
) -> POIResult | None:
    radii = search_radii_m or DEFAULT_SEARCH_RADII_METERS

    for radius in radii:
        query = build_overpass_query(lat, lon, radius, selectors)
        data = _run_overpass_query(session, query, debug=debug)
        elements = data.get("elements", []) or []

        candidates: list[POIResult] = []
        for el in elements:
            point = normalize_osm_element(el)
            if not point:
                continue

            poi_lat, poi_lon = point
            tags = el.get("tags", {}) or {}
            distance = haversine_miles(lat, lon, poi_lat, poi_lon)

            name = (
                tags.get("name")
                or tags.get("brand")
                or tags.get("operator")
                or f"Unnamed {category}"
            )

            candidates.append(
                POIResult(
                    category=category,
                    name=str(name),
                    latitude=poi_lat,
                    longitude=poi_lon,
                    distance_miles=round(distance, 2),
                    osm_type=str(el.get("type", "unknown")),
                    osm_id=el.get("id"),
                    address=build_osm_address(tags),
                    phone=tags.get("phone") or tags.get("contact:phone"),
                    website=tags.get("website") or tags.get("contact:website"),
                    raw_tags=tags,
                )
            )

        if candidates:
            candidates.sort(key=lambda x: x.distance_miles)
            return candidates[0]

    return None


def get_real_estate_metrics(
    session: requests.Session,
    zip_code: str,
    acs_year: int = DEFAULT_ACS_YEAR,
) -> dict[str, Any]:
    url = f"https://api.census.gov/data/{acs_year}/acs/acs5"
    params = {
        "get": "NAME,B25077_001E",
        "for": f"zip code tabulation area:{zip_code}",
    }
    if has_api_key("CENSUS_API_KEY"):
        params["key"] = API_KEYS["CENSUS_API_KEY"]

    resp = session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    if not isinstance(data, list) or len(data) < 2:
        raise NeighborhoodReportError(f"No ACS housing data returned for ZIP/ZCTA {zip_code}")

    header = data[0]
    row = data[1]
    mapped = dict(zip(header, row, strict=False))

    raw_value = mapped.get("B25077_001E")
    median_home_value = None

    try:
        value_int = int(raw_value)
        if value_int >= 0:
            median_home_value = value_int
    except (TypeError, ValueError):
        median_home_value = None

    return {
        "source": f"U.S. Census ACS {acs_year} 5-year",
        "zcta": zip_code,
        "label": mapped.get("NAME"),
        "median_owner_occupied_home_value_usd": median_home_value,
        "note": (
            "This is the Census median value for owner-occupied housing units in the ZIP "
            "Code Tabulation Area (ZCTA). It is not the same thing as a live MLS average sale price."
        ),
    }


def format_currency(value: int | float | None) -> str:
    if value is None:
        return "N/A"
    return f"${value:,.0f}"


def build_report_data(
    session: requests.Session,
    address: str,
    acs_year: int = DEFAULT_ACS_YEAR,
    *,
    debug: bool = False,
) -> dict[str, Any]:
    geocode = geocode_address(session, address)

    pois_config = {
        "Closest Gas Station": ["[amenity=fuel]"],
        "Closest Hospital": ["[amenity=hospital]"],
        "Closest Urgent Care": [
            '[amenity=clinic][name~"(?i)urgent"]',
            '[healthcare=clinic][name~"(?i)urgent"]',
            '[name~"(?i)urgent care"]',
        ],
        "Closest Veterinary Clinic": ["[amenity=veterinary]"],
    }

    poi_results: dict[str, Any] = {}
    errors: list[str] = []

    for label, selectors in pois_config.items():
        try:
            result = query_overpass_closest(
                session,
                lat=geocode.latitude,
                lon=geocode.longitude,
                category=label,
                selectors=selectors,
                debug=debug,
            )
            poi_results[label] = asdict(result) if result else None
        except requests.RequestException as exc:
            errors.append(f"{label}: Overpass lookup failed: {exc}")
            poi_results[label] = None

    real_estate: dict[str, Any] | None = None
    if geocode.zip_code:
        try:
            real_estate = get_real_estate_metrics(session, geocode.zip_code, acs_year=acs_year)
        except (requests.RequestException, NeighborhoodReportError) as exc:
            errors.append(f"Real estate metrics lookup failed: {exc}")
    else:
        errors.append("Could not determine ZIP code from geocoder result; skipped ACS lookup.")

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": [
            "U.S. Census Geocoder",
            f"U.S. Census ACS {acs_year} 5-year",
            "OpenStreetMap / Overpass API",
        ],
        "subject": asdict(geocode),
        "important_landmarks": {
            "closest_gas_station": poi_results.get("Closest Gas Station"),
        },
        "emergency_services": {
            "closest_hospital": poi_results.get("Closest Hospital"),
            "closest_urgent_care": poi_results.get("Closest Urgent Care"),
            "closest_veterinary_clinic": poi_results.get("Closest Veterinary Clinic"),
        },
        "real_estate_metrics": real_estate,
        "errors": errors,
    }


def poi_to_lines(poi: dict[str, Any] | None) -> list[str]:
    if not poi:
        return ["No result found."]

    lines = [
        f"Name: {poi.get('name', 'N/A')}",
        f"Distance: {poi.get('distance_miles', 'N/A')} miles",
        f"Coordinates: {poi.get('latitude', 'N/A')}, {poi.get('longitude', 'N/A')}",
    ]

    address = poi.get("address")
    if address:
        lines.append(f"Address: {address}")

    phone = poi.get("phone")
    if phone:
        lines.append(f"Phone: {phone}")

    website = poi.get("website")
    if website:
        lines.append(f"Website: {website}")

    return lines


def build_pdf(report_data: dict[str, Any], output_path: Path, *, include_debug: bool = False) -> None:
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.7 * inch,
        leftMargin=0.7 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title="Neighborhood OSINT Report",
        author="Neighborhood OSINT Report Tool",
    )

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    heading_style = styles["Heading2"]
    body_style = styles["BodyText"]
    body_style.leading = 14

    mono_style = ParagraphStyle(
        "MonoSmall",
        parent=body_style,
        fontName="Courier",
        fontSize=8.5,
        leading=10,
    )

    story: list[Any] = []

    subject = report_data["subject"]
    real_estate = report_data.get("real_estate_metrics")
    important_landmarks = report_data.get("important_landmarks", {})
    emergency_services = report_data.get("emergency_services", {})
    errors = report_data.get("errors", [])

    story.append(Paragraph("Neighborhood OSINT Report", title_style))
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph(f"Generated: {report_data.get('generated_at_utc', 'N/A')}", body_style))
    story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("Subject Property", heading_style))
    subject_rows = [
        ["Input Address", subject.get("input_address", "N/A")],
        ["Matched Address", subject.get("matched_address", "N/A")],
        ["Latitude", str(subject.get("latitude", "N/A"))],
        ["Longitude", str(subject.get("longitude", "N/A"))],
        ["ZIP Code", subject.get("zip_code") or "N/A"],
        ["City", subject.get("city") or "N/A"],
        ["State", subject.get("state") or "N/A"],
        ["County", subject.get("county") or "N/A"],
    ]
    story.append(make_table(subject_rows))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Important Landmarks", heading_style))
    gas_station = important_landmarks.get("closest_gas_station")
    for line in poi_to_lines(gas_station):
        story.append(Paragraph(escape_text(line), body_style))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Emergency Services", heading_style))
    for label, key in [
        ("Closest Hospital", "closest_hospital"),
        ("Closest Urgent Care", "closest_urgent_care"),
        ("Closest Veterinary Clinic", "closest_veterinary_clinic"),
    ]:
        story.append(Paragraph(label, styles["Heading3"]))
        for line in poi_to_lines(emergency_services.get(key)):
            story.append(Paragraph(escape_text(line), body_style))
        story.append(Spacer(1, 0.12 * inch))

    story.append(Paragraph("Real Estate Metrics", heading_style))
    if real_estate:
        story.append(
            make_table(
                [
                    ["Data Source", real_estate.get("source", "N/A")],
                    ["Geography", real_estate.get("label", "N/A")],
                    [
                        "Median Owner-Occupied Home Value",
                        format_currency(real_estate.get("median_owner_occupied_home_value_usd")),
                    ],
                ]
            )
        )
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph(escape_text(real_estate.get("note", "")), body_style))
    else:
        story.append(Paragraph("No real estate metrics available.", body_style))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Sources Used", heading_style))
    for source in report_data.get("sources", []):
        story.append(Paragraph(f"• {escape_text(source)}", body_style))
    story.append(Spacer(1, 0.2 * inch))

    if errors:
        story.append(Paragraph("Lookup Warnings / Failures", heading_style))
        for err in errors:
            story.append(Paragraph(f"• {escape_text(err)}", body_style))
        story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Raw Notes", heading_style))
    story.append(
        Paragraph(
            "This report uses publicly available information only. "
            "It is intended as a lightweight neighborhood and logistics brief, "
            "not legal, medical, insurance, appraisal, or investment advice.",
            body_style,
        )
    )
    story.append(Spacer(1, 0.12 * inch))
    story.append(
        Paragraph(
            "The real estate metric shown here is Census-based and lagging by design. "
            "It is useful as a baseline, not a crystal ball.",
            body_style,
        )
    )
    story.append(Spacer(1, 0.2 * inch))

    if include_debug:
        story.append(Paragraph("Debug Snapshot", heading_style))
        compact_json = json.dumps(report_data, indent=2)[:4000]
        for line in compact_json.splitlines():
            story.append(Paragraph(escape_text(line), mono_style))

    doc.build(story)


def make_table(rows: list[list[str]]) -> Table:
    table = Table(rows, colWidths=[2.2 * inch, 4.8 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LEADING", (0, 0), (-1, -1), 11),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
            ]
        )
    )
    return table


def escape_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_json(report_data: dict[str, Any], output_path: Path) -> None:
    output_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a neighborhood OSINT PDF report from a street address."
    )
    parser.add_argument(
        "address",
        help='Street address to investigate, e.g. "5452 Adobe Falls Rd #3, San Diego, CA 92120"',
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Output PDF path. If omitted, the filename is derived from the target address, "
            'e.g. "7978_canton_dr_lemon_grove_ca_91945.pdf".'
        ),
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="Optional path to write raw JSON results.",
    )
    parser.add_argument(
        "--acs-year",
        type=int,
        default=DEFAULT_ACS_YEAR,
        help=f"Census ACS year to use (default: {DEFAULT_ACS_YEAR})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print verbose lookup progress and include the debug snapshot in the PDF.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session = make_session()

    try:
        output_pdf = Path(args.output).expanduser().resolve() if args.output else derive_default_output_path(args.address).resolve()
        if args.debug:
            print(f"[*] Output PDF path: {output_pdf}")

        report_data = build_report_data(session, args.address, acs_year=args.acs_year, debug=args.debug)
        build_pdf(report_data, output_pdf, include_debug=args.debug)

        if args.json_out:
            output_json = Path(args.json_out).expanduser().resolve()
            write_json(report_data, output_json)
            print(f"[+] Wrote JSON: {output_json}")

        print(f"[+] Wrote PDF:  {output_pdf}")
        return 0

    except requests.HTTPError as exc:
        print(f"[!] HTTP error: {exc}", file=sys.stderr)
        return 2
    except requests.RequestException as exc:
        print(f"[!] Network error: {exc}", file=sys.stderr)
        return 3
    except NeighborhoodReportError as exc:
        print(f"[!] Report error: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:
        print(f"[!] Unexpected error: {exc}", file=sys.stderr)
        return 99


if __name__ == "__main__":
    raise SystemExit(main())
