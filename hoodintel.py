#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

from src.config import ReportOptions
from src.exceptions import NeighborhoodReportError
from src.pipeline import generate_report_data
from src.renderers.json_export import write_json
from src.renderers.pdf_reportlab import build_pdf
from src.utils import derive_default_output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a neighborhood OSINT PDF report from a street address.")
    parser.add_argument("address", help='Street address to investigate, e.g. "5452 Adobe Falls Rd #3, San Diego, CA 92120"')
    parser.add_argument("--output", default=None, help="Output PDF path (default: derived from address)")
    parser.add_argument("--json-out", default=None, help="Optional path to write raw JSON results")
    parser.add_argument("--acs-year", type=int, default=2023, help="Census ACS year to use (default: 2023)")
    parser.add_argument("--debug", action="store_true", help="Print extra progress and include debug snapshot in JSON/PDF")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output).expanduser().resolve() if args.output else derive_default_output_path(args.address).resolve()
    options = ReportOptions(
        debug=args.debug,
        include_debug_snapshot=args.debug,
        acs_year=args.acs_year,
        output_path=output_path,
        json_output_path=Path(args.json_out).expanduser().resolve() if args.json_out else None,
    )

    try:
        report = generate_report_data(args.address, options=options)
        build_pdf(report, output_path, include_debug_snapshot=options.include_debug_snapshot)
        print(f"[+] Wrote PDF: {output_path}")
        if options.json_output_path:
            write_json(report, options.json_output_path)
            print(f"[+] Wrote JSON: {options.json_output_path}")
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
    except Exception as exc:  # pragma: no cover - top-level safeguard
        print(f"[!] Unexpected error: {exc}", file=sys.stderr)
        return 99


if __name__ == "__main__":
    raise SystemExit(main())
