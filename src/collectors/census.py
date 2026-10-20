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
        # Median value; aggregate value and owner-occupied unit count (for the mean)
        "get": "NAME,B25077_001E,B25082_001E,B25081_001E",
        "for": f"zip code tabulation area:{zip_code}",
    }
    if API_KEYS.get("CENSUS_API_KEY"):
        params["key"] = API_KEYS["CENSUS_API_KEY"]

    # A missing or bad key is a redirect to an HTML page, not an HTTP error.
    response = session.get(url, params=params, timeout=config.default_timeout, allow_redirects=False)
    if response.is_redirect and "key" in response.headers.get("Location", ""):
        raise NeighborhoodReportError(
            "Census ACS needs an API key: set CENSUS_API_KEY "
            "(free at https://api.census.gov/data/key_signup.html)."
        )
    response.raise_for_status()
    if response.status_code == 204 or not response.content:
        raise NeighborhoodReportError(f"No ACS housing data returned for ZIP/ZCTA {zip_code}")
    data = response.json()
    if not isinstance(data, list) or len(data) < 2:
        raise NeighborhoodReportError(f"No ACS housing data returned for ZIP/ZCTA {zip_code}")

    header, row = data[0], data[1]
    mapped = dict(zip(header, row, strict=False))

    median_home_value = _non_negative_int(mapped.get("B25077_001E"))
    aggregate_value = _non_negative_int(mapped.get("B25082_001E"))
    owner_units = _non_negative_int(mapped.get("B25081_001E"))
    mean_home_value = round(aggregate_value / owner_units) if aggregate_value is not None and owner_units else None

    return RealEstateMetrics(
        source=f"U.S. Census ACS {acs_year} 5-year",
        zcta=zip_code,
        label=mapped.get("NAME"),
        median_owner_occupied_home_value_usd=median_home_value,
        mean_owner_occupied_home_value_usd=mean_home_value,
        note=(
            "Census values are owners' own estimates of what their homes are worth, for owner-occupied "
            "units in the ZIP Code Tabulation Area (ZCTA). The average is aggregate value divided by "
            "owner-occupied units. Neither is a sale price."
        ),
    )


def _non_negative_int(raw: object) -> int | None:
    # ACS uses large negative sentinels (e.g. -666666666) for suppressed values.
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None
