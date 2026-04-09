from __future__ import annotations

import json
from pathlib import Path

from ..models import ReportData


def write_json(report: ReportData, output_path: Path) -> None:
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
