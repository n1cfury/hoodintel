from __future__ import annotations

from ..models import ReportData


def build_basic_operating_rules(report: ReportData) -> list[str]:
    subject = report.subject.matched_address
    return [
        f"Keep the vehicle area at {subject} boring: nothing visible in the car, ever.",
        "Cover the front and side approaches before paying for fancy cloud extras.",
        "Reinforce doors before buying more gadgets.",
        "Treat indoor air quality as part of the security posture, not a side quest.",
    ]
