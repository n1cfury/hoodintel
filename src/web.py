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

from .config import ReportOptions
from .exceptions import NeighborhoodReportError
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


def get_report(address: str) -> ReportData:
    key = _cache_key(address)
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            _cache.move_to_end(key)
            return hit[1]
    report = generate_report_data(address, options=ReportOptions())
    with _cache_lock:
        _cache[key] = (now, report)
        _cache.move_to_end(key)
        while len(_cache) > CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)
    return report


def _index(error: str | None = None, address: str = "", status: int = 200) -> Response:
    html = env.get_template("index.html").render(error=error, address=address, max_len=MAX_ADDRESS_LEN)
    return Response(html, status=status, mimetype="text/html")


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
    address = " ".join((request.form.get("address") or "").split())
    fmt = request.form.get("format", "html")
    download = request.form.get("download") == "1"

    if not address:
        return _index("Enter an address.", status=400)
    if len(address) > MAX_ADDRESS_LEN:
        return _index(f"Address is too long (max {MAX_ADDRESS_LEN} characters).", address[:MAX_ADDRESS_LEN], 400)
    if fmt not in ("html", "json"):
        return _index("Unknown output format.", address, 400)

    try:
        data = get_report(address)
    except NeighborhoodReportError as exc:
        return _index(str(exc), address, 422)
    except requests.RequestException as exc:
        app.logger.warning("upstream error for report: %s", exc)
        return _index("A public data source didn't respond. Try again in a minute.", address, 502)

    if fmt == "json":
        resp = Response(json.dumps(data.to_dict(), indent=2), mimetype="application/json")
    else:
        resp = Response(render_report(data, web=not download), mimetype="text/html")
    if download:
        resp.headers["Content-Disposition"] = f'attachment; filename="{slugify_address(address)}.{fmt}"'
    return resp


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Development server. Use a WSGI server (e.g. gunicorn) for anything shared.
    Flask's debug mode is never enabled: its debugger allows code execution."""
    app.run(host=host, port=port, debug=False, threaded=True)
