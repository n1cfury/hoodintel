from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

import requests

from .analysis.rules import build_basic_operating_rules
from .analysis.summarizer import build_executive_summary
from .config import AppConfig, ReportOptions
from .exceptions import NeighborhoodReportError
from .models import LookupWarning, ReportData
from .collectors.airports import AIRPORTS_SOURCE, closest_airport
from .collectors.census import get_real_estate_metrics
from .collectors.elevation import USGS_SOURCE, get_elevation
from .collectors.geocode import geocode_address
from .collectors.pois import find_closest_pois
from .collectors.zillow import ZHVI_SOURCE, get_home_value_index
from .http import make_session


def generate_report_data(
    address: str,
    *,
    options: ReportOptions | None = None,
    config: AppConfig | None = None,
    session: requests.Session | None = None,
) -> ReportData:
    options = options or ReportOptions()
    config = config or AppConfig(acs_year=options.acs_year)
    session = session or make_session(config)

    geocode = geocode_address(session, address, config)

    warnings: list[LookupWarning] = []
    if geocode.source != "U.S. Census Geocoder":
        note = f", {geocode.precision}" if geocode.precision else ""
        warnings.append(LookupWarning(source="Geocoder", message=f"No Census match; location from {geocode.source}{note}."))

    poi_results, poi_errors = find_closest_pois(
        session, lat=geocode.latitude, lon=geocode.longitude, config=config
    )
    warnings.extend(LookupWarning(source="OpenStreetMap", message=msg) for msg in poi_errors)

    elevation = None
    try:
        elevation = get_elevation(session, geocode.latitude, geocode.longitude, config)
    except (requests.RequestException, NeighborhoodReportError) as exc:
        warnings.append(LookupWarning(source="Elevation", message=str(exc)))

    real_estate = None
    home_value = None
    if geocode.zip_code:
        try:
            home_value = get_home_value_index(session, geocode.zip_code, config)
        except (requests.RequestException, NeighborhoodReportError, OSError) as exc:
            warnings.append(LookupWarning(source="Zillow", message=str(exc)))
        try:
            real_estate = get_real_estate_metrics(session, geocode.zip_code, options.acs_year, config)
        except (requests.RequestException, NeighborhoodReportError) as exc:
            warnings.append(LookupWarning(source="ACS", message=str(exc)))
    else:
        warnings.append(LookupWarning(source="Real estate", message="No ZIP code determined from geocoder result."))

    report = ReportData(
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        sources=[
            geocode.source,
            USGS_SOURCE,
            "OpenStreetMap (Nominatim, Overpass API)",
            AIRPORTS_SOURCE,
            ZHVI_SOURCE,
            f"U.S. Census ACS {options.acs_year} 5-year",
        ],
        subject=geocode,
        important_landmarks={
            "closest_grocery_store": poi_results.get("Closest Grocery Store"),
            "closest_school": poi_results.get("Closest School"),
            "closest_gas_station": poi_results.get("Closest Gas Station"),
            "closest_airport": closest_airport(geocode.latitude, geocode.longitude),
        },
        emergency_services={
            "closest_hospital": poi_results.get("Closest Hospital"),
            "closest_urgent_care": poi_results.get("Closest Urgent Care"),
            "closest_fire_station": poi_results.get("Closest Fire Station"),
            "closest_veterinary_clinic": poi_results.get("Closest Veterinary Clinic"),
        },
        real_estate_metrics=real_estate,
        home_value_index=home_value,
        elevation=elevation,
        warnings=warnings,
    )
    report.executive_summary = build_executive_summary(report)
    report.operating_rules = build_basic_operating_rules(report)
    if options.debug or options.include_debug_snapshot:
        report.debug_snapshot = report.to_dict()
    return report
