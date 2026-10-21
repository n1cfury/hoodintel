"""Browser front end: address form -> HTML report (or JSON).

Local:      python hoodintel.py --serve
Server:     gunicorn -b 0.0.0.0:8000 src.web:app
"""
from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict

import requests
from flask import Flask, Response, request

from . import audit
from .config import ReportOptions
from .collectors.zillow import ensure_zhvi_cache
from .exceptions import NeighborhoodReportError
from .http import make_session
from .models import ReportData
from .pipeline import generate_report_data
from .renderers.html import env, render_report
from .utils import slugify_address

MAX_ADDRESS_LEN = 200
CACHE_TTL_SECONDS = 3600
CACHE_MAX_ENTRIES = 64

app = Flask(__name__)

# Reports are cached briefly so the download buttons don't re-run every
# lookup, and so repeat requests don't hammer the free Overpass servers.
_cache: OrderedDict[str, tuple[float, ReportData]] = OrderedDict()
_cache_lock = threading.Lock()


def _cache_key(address: str) -> str:
    return " ".join(address.upper().split())


def get_report(address: str) -> tuple[ReportData, bool]:
    """The report and whether it came from the cache."""
    key = _cache_key(address)
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            _cache.move_to_end(key)
            return hit[1], True
    report = generate_report_data(address, options=ReportOptions())
    with _cache_lock:
        _cache[key] = (now, report)
        _cache.move_to_end(key)
        while len(_cache) > CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)
    return report, False


def _index(error: str | None = None, address: str = "", status: int = 200) -> Response:
    html = env.get_template("index.html").render(
        error=error, address=address, max_len=MAX_ADDRESS_LEN, audit_enabled=audit.enabled()
    )
    return Response(html, status=status, mimetype="text/html")


def _audit(address: str, outcome: str, started: float, **fields) -> None:
    audit.record(audit.AuditEntry(
        queried_address=address[:MAX_ADDRESS_LEN] if address else "(empty)",
        outcome=outcome,
        source="web",
        duration_ms=round((time.monotonic() - started) * 1000),
        client=request.remote_addr,
        **fields,
    ))


@app.after_request
def _security_headers(resp: Response) -> Response:
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Cache-Control", "no-store")
    return resp


@app.get("/")
def index() -> Response:
    return _index()


@app.get("/healthz")
def healthz() -> Response:
    return Response("ok", mimetype="text/plain")


@app.post("/report")
def report() -> Response:
    started = time.monotonic()
    address = " ".join((request.form.get("address") or "").split())
    fmt = request.form.get("format", "html")
    download = request.form.get("download") == "1"
    common = {"output_format": fmt if fmt in ("html", "json") else None, "download": download}

    rejection = None
    if not address:
        rejection = "Enter an address."
    elif len(address) > MAX_ADDRESS_LEN:
        rejection = f"Address is too long (max {MAX_ADDRESS_LEN} characters)."
    elif fmt not in ("html", "json"):
        rejection = "Unknown output format."
    if rejection:
        _audit(address, "rejected", started, detail=rejection, **common)
        return _index(rejection, address[:MAX_ADDRESS_LEN], 400)

    try:
        data, cached = get_report(address)
    except NeighborhoodReportError as exc:
        _audit(address, "not_found", started, detail=str(exc), **common)
        return _index(str(exc), address, 422)
    except requests.RequestException as exc:
        app.logger.warning("upstream error for report: %s", exc)
        _audit(address, "upstream_error", started, detail=str(exc), **common)
        return _index("A public data source didn't respond. Try again in a minute.", address, 502)

    if fmt == "json":
        resp = Response(json.dumps(data.to_dict(), indent=2), mimetype="application/json")
    else:
        resp = Response(render_report(data, web=not download), mimetype="text/html")
    if download:
        resp.headers["Content-Disposition"] = f'attachment; filename="{slugify_address(address)}.{fmt}"'
    _audit(address, "ok", started, matched_address=data.subject.matched_address,
           generated_at=data.generated_at_utc, cached=cached, **common)
    return resp


HISTORY_PAGE_SIZE = 100


@app.get("/history")
def history() -> Response:
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1
    rows, total = audit.recent(HISTORY_PAGE_SIZE, (page - 1) * HISTORY_PAGE_SIZE)
    html = env.get_template("history.html").render(
        rows=rows,
        total=total,
        page=page,
        pages=max(1, -(-total // HISTORY_PAGE_SIZE)),
        enabled=audit.enabled(),
        db_path=str(audit.db_path()),
        labels=audit.OUTCOME_LABELS,
    )
    return Response(html, mimetype="text/html")


@app.get("/history.csv")
def history_csv() -> Response:
    resp = Response(audit.export_csv(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = 'attachment; filename="hoodintel-history.csv"'
    return resp


def warm_caches() -> None:
    """Fetch the Zillow ZIP file in the background, so the first report
    doesn't wait ~20 s for it. Failures are left for the report to surface."""

    def run() -> None:
        try:
            ensure_zhvi_cache(make_session())
        except Exception as exc:  # noqa: BLE001 - background best effort
            app.logger.warning("Zillow cache warm-up failed: %s", exc)

    threading.Thread(target=run, name="warm-caches", daemon=True).start()


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Development server. Use a WSGI server (e.g. gunicorn) for anything shared.
    Flask's debug mode is never enabled: its debugger allows code execution."""
    warm_caches()
    app.run(host=host, port=port, debug=False, threaded=True)
