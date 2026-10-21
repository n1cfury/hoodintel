"""ZIP-level typical home value from the Zillow Home Value Index (ZHVI).

Zillow publishes ZHVI as one ~120 MB CSV covering every ZIP and month. It's
downloaded at most once a month, reduced to one row per ZIP (latest month
and the month a year earlier), and cached as a small CSV.

Cache folder: $HOODINTEL_CACHE_DIR, else ~/.cache/hoodintel.
"""
from __future__ import annotations

import csv
import os
import re
import threading
import time
from functools import lru_cache
from pathlib import Path

import requests

from ..config import AppConfig
from ..exceptions import NeighborhoodReportError
from ..models import HomeValueIndex

ZHVI_URL = (
    "https://files.zillowstatic.com/research/public_csvs/zhvi/"
    "Zip_zhvi_uc_sfrcondo_tier_0.33_0.67_sm_sa_month.csv"
)
ZHVI_SOURCE = "Zillow Home Value Index (ZHVI), all homes, smoothed & seasonally adjusted"
MAX_AGE_SECONDS = 30 * 24 * 3600
DOWNLOAD_TIMEOUT = 300
CACHE_FIELDS = ["zip", "region", "as_of", "value", "year_ago"]
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_lock = threading.Lock()


def cache_dir() -> Path:
    configured = os.getenv("HOODINTEL_CACHE_DIR", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".cache" / "hoodintel"


def cache_path() -> Path:
    return cache_dir() / "zhvi_zip.csv"


def _is_fresh(path: Path) -> bool:
    return path.exists() and time.time() - path.stat().st_mtime < MAX_AGE_SECONDS


def _to_int(value: str) -> int | None:
    try:
        return round(float(value))
    except ValueError:
        return None


def download_zhvi(session: requests.Session, dest: Path) -> int:
    """Stream the full ZHVI CSV and write the reduced per-ZIP cache. Returns row count."""
    tmp = dest.with_suffix(".tmp")
    dest.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with session.get(ZHVI_URL, stream=True, timeout=DOWNLOAD_TIMEOUT) as response:
        response.raise_for_status()
        response.encoding = "utf-8"  # served without a charset; iter_lines would yield bytes
        reader = csv.reader(response.iter_lines(decode_unicode=True))
        header = next(reader)
        dates = [i for i, name in enumerate(header) if _DATE.match(name)]
        col = {name: i for i, name in enumerate(header)}
        with tmp.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(CACHE_FIELDS)
            for row in reader:
                latest = next((i for i in reversed(dates) if i < len(row) and row[i]), None)
                if latest is None:
                    continue
                year_ago_idx = latest - 12
                year_ago = row[year_ago_idx] if year_ago_idx in dates and row[year_ago_idx] else ""
                place = ", ".join(p for p in [row[col["City"]], row[col["State"]]] if p)
                metro = row[col["Metro"]]
                region = f"{place} ({metro})" if metro and metro not in place else place
                rounded = [str(_to_int(v)) if v else "" for v in (row[latest], year_ago)]
                writer.writerow([row[col["RegionName"]].zfill(5), region, header[latest], *rounded])
                count += 1
    if count < 1000:  # truncated or changed upstream file: keep the old cache
        tmp.unlink(missing_ok=True)
        raise NeighborhoodReportError(f"Zillow ZHVI download looked incomplete ({count} ZIPs).")
    tmp.replace(dest)
    _load.cache_clear()
    return count


def ensure_zhvi_cache(session: requests.Session, *, force: bool = False) -> Path:
    """Download if missing or older than a month. A stale cache is kept when
    the refresh fails; only a missing cache is an error."""
    path = cache_path()
    with _lock:
        if force or not _is_fresh(path):
            try:
                download_zhvi(session, path)
            except (requests.RequestException, NeighborhoodReportError, OSError):
                if not path.exists():
                    raise
    return path


@lru_cache(maxsize=1)
def _load(path: str, mtime: float) -> dict[str, list[str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader)
        return {row[0]: row for row in reader}


def get_home_value_index(
    session: requests.Session, zip_code: str, config: AppConfig | None = None
) -> HomeValueIndex:
    path = ensure_zhvi_cache(session)
    row = _load(str(path), path.stat().st_mtime).get(zip_code.zfill(5))
    if row is None:
        raise NeighborhoodReportError(f"Zillow has no home value index for ZIP {zip_code}.")
    _, region, as_of, value, year_ago = row
    current, previous = _to_int(value), _to_int(year_ago) if year_ago else None
    if current is None:
        raise NeighborhoodReportError(f"Zillow has no home value index for ZIP {zip_code}.")
    change = round((current - previous) / previous * 100, 1) if previous else None
    return HomeValueIndex(
        source=ZHVI_SOURCE,
        zip_code=zip_code,
        region=region or None,
        typical_home_value_usd=current,
        as_of=as_of[:7],
        year_ago_value_usd=previous,
        change_1y_pct=change,
    )
