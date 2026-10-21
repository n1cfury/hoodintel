"""Request history: one row per report request, web or CLI, in SQLite.

Location: $HOODINTEL_AUDIT_DB, else ~/.local/share/hoodintel/audit.db.
In a container, point it at a mounted volume so history survives restarts.
Set HOODINTEL_AUDIT=0 to turn logging (and the history page) off.

Logging never breaks a report: write errors are reported and swallowed.
"""
from __future__ import annotations

import csv
import io
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    requested_at    TEXT NOT NULL,      -- UTC ISO 8601, when the request came in
    generated_at    TEXT,               -- UTC ISO 8601, when the report data was built
    source          TEXT NOT NULL,      -- web | cli
    queried_address TEXT NOT NULL,
    matched_address TEXT,
    outcome         TEXT NOT NULL,      -- ok | not_found | upstream_error | rejected | error
    detail          TEXT,               -- error message, if any
    output_format   TEXT,               -- html | json
    download        INTEGER NOT NULL DEFAULT 0,
    cached          INTEGER NOT NULL DEFAULT 0,
    duration_ms     INTEGER,
    client          TEXT                -- remote address for web requests
);
CREATE INDEX IF NOT EXISTS requests_requested_at ON requests (requested_at);
"""
CSV_FIELDS = [
    "id", "requested_at", "generated_at", "source", "queried_address", "matched_address", "outcome",
    "detail", "output_format", "download", "cached", "duration_ms", "client",
]
OUTCOME_LABELS = {
    "ok": "Report generated",
    "not_found": "Address not found",
    "upstream_error": "Data source error",
    "rejected": "Invalid input",
    "error": "Error",
}


@dataclass(slots=True)
class AuditEntry:
    queried_address: str
    outcome: str
    source: str = "web"
    matched_address: str | None = None
    generated_at: str | None = None
    detail: str | None = None
    output_format: str | None = None
    download: bool = False
    cached: bool = False
    duration_ms: int | None = None
    client: str | None = None


def enabled() -> bool:
    return os.getenv("HOODINTEL_AUDIT", "1").strip().lower() not in ("0", "false", "no", "off")


def db_path() -> Path:
    configured = os.getenv("HOODINTEL_AUDIT_DB", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".local" / "share" / "hoodintel" / "audit.db"


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # concurrent web threads/workers
    conn.executescript(SCHEMA)
    return conn


def record(entry: AuditEntry) -> None:
    if not enabled():
        return
    row = {
        "requested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_at": entry.generated_at,
        "source": entry.source,
        "queried_address": entry.queried_address,
        "matched_address": entry.matched_address,
        "outcome": entry.outcome,
        "detail": (entry.detail or None) and entry.detail[:500],
        "output_format": entry.output_format,
        "download": int(entry.download),
        "cached": int(entry.cached),
        "duration_ms": entry.duration_ms,
        "client": entry.client,
    }
    try:
        with _connect() as conn:
            conn.execute(
                f"INSERT INTO requests ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})",
                tuple(row.values()),
            )
    except (sqlite3.Error, OSError) as exc:
        print(f"[!] Audit log write failed ({db_path()}): {exc}", file=sys.stderr)


def recent(limit: int = 100, offset: int = 0) -> tuple[list[sqlite3.Row], int]:
    """Newest first, plus the total row count."""
    if not enabled() or not db_path().exists():
        return [], 0
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM requests ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
    return rows, total


def _csv_safe(value: object) -> object:
    # Spreadsheet apps run cells starting with these as formulas; addresses are user input.
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def export_csv() -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_FIELDS)
    if enabled() and db_path().exists():
        with _connect() as conn:
            for row in conn.execute(f"SELECT {', '.join(CSV_FIELDS)} FROM requests ORDER BY id"):
                writer.writerow([_csv_safe(row[f]) for f in CSV_FIELDS])
    return out.getvalue()
