from __future__ import annotations

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
