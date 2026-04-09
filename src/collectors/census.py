from __future__ import annotations

import requests

from ..config import API_KEYS, AppConfig
from ..exceptions import NeighborhoodReportError
from ..models import RealEstateMetrics


def get_real_estate_metrics(
    session: requests.Session,
    zip_code: str,
    acs_year: int,
    config: AppConfig | None = None,
) -> RealEstateMetrics:
    config = config or AppConfig()
    url = f"https://api.census.gov/data/{acs_year}/acs/acs5"
    params = {
        "get": "NAME,B25077_001E",
        "for": f"zip code tabulation area:{zip_code}",
    }
    if API_KEYS.get("CENSUS_API_KEY"):
        params["key"] = API_KEYS["CENSUS_API_KEY"]

    response = session.get(url, params=params, timeout=config.default_timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list) or len(data) < 2:
        raise NeighborhoodReportError(f"No ACS housing data returned for ZIP/ZCTA {zip_code}")

    header, row = data[0], data[1]
    mapped = dict(zip(header, row, strict=False))

    raw_value = mapped.get("B25077_001E")
    median_home_value = None
    try:
        value_int = int(raw_value)
        if value_int >= 0:
            median_home_value = value_int
    except (TypeError, ValueError):
        median_home_value = None

    return RealEstateMetrics(
        source=f"U.S. Census ACS {acs_year} 5-year",
        zcta=zip_code,
        label=mapped.get("NAME"),
        median_owner_occupied_home_value_usd=median_home_value,
        note=(
            "This is the Census median value for owner-occupied housing units in the ZIP Code "
            "Tabulation Area (ZCTA). It is not the same thing as a live MLS average sale price."
        ),
    )
