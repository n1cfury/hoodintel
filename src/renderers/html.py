"""ReportData -> standalone HTML. No network, no source-specific logic."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from ..models import ReportData

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,           # OSM tags and geocoder output are untrusted
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def _safe_url(url: Any) -> str | None:
    """Autoescape doesn't stop javascript: hrefs; only allow http(s) links.
    OSM website tags are often plain http, so http is allowed here."""
    if not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    return url.strip() if parts.scheme in ("http", "https") and parts.netloc else None


def _usd(v: Any) -> str:
    return f"${v:,.0f}" if isinstance(v, (int, float)) else "—"


def _osm_url(poi: dict[str, Any]) -> str | None:
    if poi.get("osm_type") in ("node", "way", "relation") and poi.get("osm_id"):
        return f"https://www.openstreetmap.org/{poi['osm_type']}/{int(poi['osm_id'])}"
    return None


def _map_url(lat: Any, lon: Any, zoom: int = 16) -> str | None:
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map={zoom}/{lat:.6f}/{lon:.6f}"


env.filters["safe_url"] = _safe_url
env.filters["usd"] = _usd
env.filters["osm_url"] = _osm_url
env.globals["map_url"] = _map_url


def render_report(report: ReportData, *, web: bool = False) -> str:
    """`web=True` adds the toolbar (new report / download) used by the web UI."""
    return env.get_template("report.html").render(r=report.to_dict(), web=web)


def write_report(report: ReportData, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_report(report), encoding="utf-8")
    return output_path
