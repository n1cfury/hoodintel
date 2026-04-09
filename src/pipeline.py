from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

import requests

from .analysis.hardening import build_basic_hardening_plan, build_basic_operating_rules
from .analysis.summarizer import build_executive_summary
from .config import AppConfig, POI_QUERIES, ReportOptions
from .exceptions import NeighborhoodReportError
from .models import LookupWarning, ReportData
from .collectors.census import get_real_estate_metrics
from .collectors.geocode import geocode_address
from .collectors.pois import query_overpass_closest
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

    poi_results = {}
    warnings: list[LookupWarning] = []
    for label, selectors in POI_QUERIES.items():
        try:
            poi_results[label] = query_overpass_closest(
                session,
                lat=geocode.latitude,
                lon=geocode.longitude,
                category=label,
                selectors=selectors,
                config=config,
            )
        except requests.RequestException as exc:
            warnings.append(LookupWarning(source=label, message=str(exc)))
            poi_results[label] = None

    real_estate = None
    if geocode.zip_code:
        try:
            real_estate = get_real_estate_metrics(session, geocode.zip_code, options.acs_year, config)
        except (requests.RequestException, NeighborhoodReportError) as exc:
            warnings.append(LookupWarning(source="ACS", message=str(exc)))
    else:
        warnings.append(LookupWarning(source="ACS", message="No ZIP code determined from geocoder result."))

    report = ReportData(
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        sources=[
            "U.S. Census Geocoder",
            f"U.S. Census ACS {options.acs_year} 5-year",
            "OpenStreetMap / Overpass API",
        ],
        subject=geocode,
        important_landmarks={
            "closest_gas_station": poi_results.get("Closest Gas Station"),
        },
        emergency_services={
            "closest_hospital": poi_results.get("Closest Hospital"),
            "closest_urgent_care": poi_results.get("Closest Urgent Care"),
            "closest_veterinary_clinic": poi_results.get("Closest Veterinary Clinic"),
        },
        real_estate_metrics=real_estate,
        warnings=warnings,
    )
    report.executive_summary = build_executive_summary(report)
    report.hardening_plan = build_basic_hardening_plan(report)
    report.operating_rules = build_basic_operating_rules(report)
    if options.debug or options.include_debug_snapshot:
        report.debug_snapshot = report.to_dict()
    return report
