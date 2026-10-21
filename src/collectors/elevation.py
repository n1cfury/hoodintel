from __future__ import annotations

import requests

from ..config import AppConfig
from ..exceptions import NeighborhoodReportError
from ..models import Elevation

USGS_EPQS_URL = "https://epqs.nationalmap.gov/v1/json"
USGS_SOURCE = "USGS 3DEP Elevation Point Query Service"
FEET_PER_METER = 3.28084


def get_elevation(session: requests.Session, lat: float, lon: float, config: AppConfig | None = None) -> Elevation:
    """Ground elevation from the USGS 3D Elevation Program. U.S. only, no key."""
    config = config or AppConfig()
    params = {"x": lon, "y": lat, "wkid": 4326, "units": "Feet", "includeDate": "false"}
    response = session.get(USGS_EPQS_URL, params=params, timeout=config.default_timeout)
    response.raise_for_status()
    try:
        feet = float(response.json()["value"])
    except (KeyError, TypeError, ValueError):
        raise NeighborhoodReportError("USGS returned no elevation for this location.") from None
    if feet <= -1_000_000:  # EPQS's no-data sentinel (-1000000) for points off its rasters
        raise NeighborhoodReportError("USGS has no elevation data for this location.")
    return Elevation(feet=round(feet, 1), meters=round(feet / FEET_PER_METER, 1), source=USGS_SOURCE)
