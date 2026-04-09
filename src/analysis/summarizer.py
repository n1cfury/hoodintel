from __future__ import annotations

from ..models import ReportData


def build_executive_summary(report: ReportData) -> list[str]:
    subject = report.subject
    summary = [
        f"Target property: {subject.matched_address}.",
        "This report is intended to be a lightweight public-source neighborhood and logistics brief.",
    ]

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

    if report.real_estate_metrics and report.real_estate_metrics.median_owner_occupied_home_value_usd:
        value = report.real_estate_metrics.median_owner_occupied_home_value_usd
        summary.append(f"ZIP-level Census baseline for owner-occupied home value: ${value:,.0f}.")

    return summary
