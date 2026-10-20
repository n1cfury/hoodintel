from __future__ import annotations

from ..models import ReportData


def build_executive_summary(report: ReportData) -> list[str]:
    subject = report.subject
    summary = [
        f"Target property: {subject.matched_address}.",
        "This report is intended to be a lightweight public-source neighborhood and logistics brief.",
    ]

    if report.elevation:
        feet = report.elevation.feet
        where = "above" if feet > 0 else "below" if feet < 0 else "at"
        summary.append(f"Elevation: {abs(feet):,.0f} ft {where} sea level.")

    airport = report.important_landmarks.get("closest_airport")
    if airport:
        summary.append(f"Closest regional/international airport: {airport.name}, roughly {airport.distance_miles} miles.")

    fire = report.emergency_services.get("closest_fire_station")
    if fire:
        summary.append(f"Closest fire station identified at roughly {fire.distance_miles} miles.")

    gas_station = report.important_landmarks.get("closest_gas_station")
    if gas_station:
        summary.append(
            f"Closest gas station identified at roughly {gas_station.distance_miles} miles."
        )

    vet = report.emergency_services.get("closest_veterinary_clinic")
    if vet:
        summary.append(
            f"Closest veterinary clinic identified at roughly {vet.distance_miles} miles."
        )

    hvi = report.home_value_index
    if hvi:
        change = f" ({hvi.change_1y_pct:+.1f}% over 1 year)" if hvi.change_1y_pct is not None else ""
        summary.append(f"Typical home value in ZIP {hvi.zip_code}: ${hvi.typical_home_value_usd:,.0f}{change}, Zillow, {hvi.as_of}.")

    acs = report.real_estate_metrics
    if acs and acs.mean_owner_occupied_home_value_usd:
        summary.append(f"Census average owner-occupied home value: ${acs.mean_owner_occupied_home_value_usd:,.0f}.")
    elif acs and acs.median_owner_occupied_home_value_usd:
        summary.append(f"Census median owner-occupied home value: ${acs.median_owner_occupied_home_value_usd:,.0f}.")

    return summary
