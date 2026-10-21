#!/usr/bin/env python3
"""HoodIntel: street address -> neighborhood OSINT report as standalone HTML.

Usage:
    python hoodintel.py "1234 Example St, San Diego, CA 92101"   # write an HTML report
    python hoodintel.py --serve                                  # run the web UI
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

from src import audit
from src.config import ReportOptions
from src.exceptions import NeighborhoodReportError
from src.pipeline import generate_report_data
from src.renderers.html import write_report
from src.renderers.json_export import write_json
from src.utils import derive_default_output_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a neighborhood OSINT HTML report from a street address.")
    parser.add_argument("address", nargs="?", help='Street address to investigate, e.g. "1234 Example St, San Diego, CA 92101"')
    parser.add_argument("--output", default=None, help="Output HTML path (default: derived from address)")
    parser.add_argument("--json-out", default=None, help="Optional path to write raw JSON results")
    parser.add_argument("--acs-year", type=int, default=2023, help="Census ACS year to use (default: 2023)")
    parser.add_argument("--debug", action="store_true", help="Include a debug snapshot in the JSON/HTML report")
    parser.add_argument("--update-data", action="store_true",
                        help="Download/refresh the Zillow home value cache now, then exit")
    web = parser.add_argument_group("web UI")
    web.add_argument("--serve", action="store_true", help="Run the browser UI instead of writing a report")
    web.add_argument("--host", default="127.0.0.1", help="Address to listen on (default: 127.0.0.1)")
    web.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    args = parser.parse_args(argv)
    if not (args.serve or args.update_data or args.address):
        parser.error("an address is required (or use --serve / --update-data)")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.update_data:
        from src.collectors.zillow import cache_path, download_zhvi
        from src.http import make_session

        print("[*] Downloading Zillow ZHVI (~120 MB)...")
        try:
            count = download_zhvi(make_session(), cache_path())
        except (requests.RequestException, NeighborhoodReportError, OSError) as exc:
            print(f"[!] Update failed: {exc}", file=sys.stderr)
            return 3
        print(f"[+] Cached {count:,} ZIPs in {cache_path()}")
        return 0

    if args.serve:
        from src.web import serve

        print(f"[+] HoodIntel web UI on http://{args.host}:{args.port}/  (Ctrl+C to stop)")
        serve(host=args.host, port=args.port)
        return 0

    output_path = Path(args.output).expanduser().resolve() if args.output else derive_default_output_path(args.address).resolve()
    options = ReportOptions(
        debug=args.debug,
        include_debug_snapshot=args.debug,
        acs_year=args.acs_year,
        output_path=output_path,
        json_output_path=Path(args.json_out).expanduser().resolve() if args.json_out else None,
    )

    started = time.monotonic()

    def log(outcome: str, **fields) -> None:
        audit.record(audit.AuditEntry(
            queried_address=args.address, outcome=outcome, source="cli", output_format="html",
            duration_ms=round((time.monotonic() - started) * 1000), **fields,
        ))

    try:
        report = generate_report_data(args.address, options=options)
        write_report(report, output_path)
        print(f"[+] Wrote HTML: {output_path}")
        if options.json_output_path:
            write_json(report, options.json_output_path)
            print(f"[+] Wrote JSON: {options.json_output_path}")
        log("ok", matched_address=report.subject.matched_address, generated_at=report.generated_at_utc)
        return 0
    except requests.HTTPError as exc:
        log("upstream_error", detail=str(exc))
        print(f"[!] HTTP error: {exc}", file=sys.stderr)
        return 2
    except requests.RequestException as exc:
        log("upstream_error", detail=str(exc))
        print(f"[!] Network error: {exc}", file=sys.stderr)
        return 3
    except NeighborhoodReportError as exc:
        log("not_found", detail=str(exc))
        print(f"[!] Report error: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:  # pragma: no cover - top-level safeguard
        log("error", detail=str(exc))
        print(f"[!] Unexpected error: {exc}", file=sys.stderr)
        return 99

if __name__ == "__main__":
    raise SystemExit(main())
