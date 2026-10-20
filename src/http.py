from __future__ import annotations

import threading
import time

import requests

from .config import AppConfig


def make_session(config: AppConfig | None = None) -> requests.Session:
    config = config or AppConfig()
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": config.user_agent,
            "Accept": "application/json,text/plain,*/*",
        }
    )
    return session


# Per-host minimum spacing between requests, shared across threads so the
# web UI's concurrent reports still respect each service's usage policy.
MIN_INTERVAL = {"nominatim.openstreetmap.org": 1.1}
_last_request: dict[str, float] = {}
_throttle_lock = threading.Lock()


def throttle(host: str) -> None:
    interval = MIN_INTERVAL.get(host)
    if not interval:
        return
    with _throttle_lock:
        now = time.monotonic()
        wait = _last_request.get(host, 0.0) + interval - now
        _last_request[host] = now + max(wait, 0.0)
    if wait > 0:
        time.sleep(wait)
