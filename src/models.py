from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any


@dataclass(slots=True)
class GeocodeResult:
    input_address: str
    matched_address: str
    latitude: float
    longitude: float
    zip_code: str | None
    city: str | None
    state: str | None
    county: str | None = None
    source: str = "U.S. Census Geocoder"
    precision: str | None = None  # set when the match is approximate


@dataclass(slots=True)
class POIResult:
    category: str
    name: str
    latitude: float
    longitude: float
    distance_miles: float
    osm_type: str
    osm_id: int | None
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    raw_tags: dict[str, Any] | None = None
    detail: str | None = None  # short extra line, e.g. an airport's IATA code and size


@dataclass(slots=True)
class RealEstateMetrics:
    source: str
    zcta: str
    label: str | None
    median_owner_occupied_home_value_usd: int | None
    note: str
    mean_owner_occupied_home_value_usd: int | None = None


@dataclass(slots=True)
class HomeValueIndex:
    source: str
    zip_code: str
    region: str | None
    typical_home_value_usd: int
    as_of: str
    year_ago_value_usd: int | None = None
    change_1y_pct: float | None = None


@dataclass(slots=True)
class Elevation:
    feet: float
    meters: float
    source: str


@dataclass(slots=True)
class LookupWarning:
    source: str
    message: str


@dataclass(slots=True)
class ReportData:
    generated_at_utc: str
    sources: list[str]
    subject: GeocodeResult
    important_landmarks: dict[str, POIResult | None]
    emergency_services: dict[str, POIResult | None]
    real_estate_metrics: RealEstateMetrics | None = None
    home_value_index: HomeValueIndex | None = None
    elevation: Elevation | None = None
    executive_summary: list[str] = field(default_factory=list)
    operating_rules: list[str] = field(default_factory=list)
    warnings: list[LookupWarning] = field(default_factory=list)
    debug_snapshot: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        def convert(value: Any) -> Any:
            if is_dataclass(value):
                return {k: convert(v) for k, v in asdict(value).items()}
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            if isinstance(value, list):
                return [convert(item) for item in value]
            return value

        return convert(self)
