from __future__ import annotations

from ..models import HardeningRecommendation, ReportData


def build_basic_hardening_plan(report: ReportData) -> list[HardeningRecommendation]:
    """Return a conservative baseline plan until more location-specific signals are added."""
    return [
        HardeningRecommendation(
            item="Video doorbell",
            quantity="1",
            deploy_where="Front entry / porch",
            rationale="Captures approach behavior, package activity, and unknown knocks.",
        ),
        HardeningRecommendation(
            item="Exterior cameras",
            quantity="4",
            deploy_where="Driveway, front corner, side gate, rear approach",
            rationale="Gives approach coverage and supports incident review.",
        ),
        HardeningRecommendation(
            item="Motion floodlights",
            quantity="2-3",
            deploy_where="Driveway, side gate, back edge",
            rationale="Improves night visibility and deters casual trespass.",
        ),
        HardeningRecommendation(
            item="Door reinforcement kits",
            quantity="2-3 doors",
            deploy_where="Front, side/rear, garage-to-house",
            rationale="Cheap structural upgrade with a disproportionately good payoff.",
        ),
        HardeningRecommendation(
            item="HEPA purifiers",
            quantity="2",
            deploy_where="Primary bedroom and main living area",
            rationale="Helps with particulates, dust, and general indoor air quality.",
        ),
    ]


def build_basic_operating_rules(report: ReportData) -> list[str]:
    subject = report.subject.matched_address
    return [
        f"Keep the vehicle area at {subject} boring: nothing visible in the car, ever.",
        "Cover the front and side approaches before paying for fancy cloud extras.",
        "Reinforce doors before buying more gadgets.",
        "Treat indoor air quality as part of the security posture, not a side quest.",
    ]
