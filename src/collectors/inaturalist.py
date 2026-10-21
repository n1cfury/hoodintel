"""Flora and fauna around the address, from research-grade iNaturalist
observations (no key). Species are ranked by how often they've been
observed nearby, which reflects what people notice and photograph, not
abundance.
"""
from __future__ import annotations

from typing import Any

import requests

from ..config import AppConfig
from ..http import throttle
from ..models import Environment, Species

INAT_HOST = "api.inaturalist.org"
INAT_API = f"https://{INAT_HOST}/v1"
INAT_SOURCE = "iNaturalist research-grade observations"
SEARCH_RADIUS_KM = 15
TOP_N = 8
INTRODUCED_SHOWN = 12
INTRODUCED_FETCHED = 200  # enough to tag introduced species in the other lists

# Groups that are (almost) all trees. Families like willows and birches
# include a few shrubs; close enough for a neighborhood brief.
TREE_TAXA = {
    136329: "conifers",
    47852: "oaks, beeches",
    48867: "palms",
    47567: "willows, poplars",
    49155: "birches, alders",
    54497: "walnuts, hickories",
    53548: "elms",
    49663: "sycamores",
    53581: "magnolias",
    47727: "maples",
    54806: "ashes",
    51815: "eucalyptus",
}
VENOMOUS_SNAKES = {30667: "vipers (rattlesnakes, copperheads, cottonmouths)", 30403: "elapids (coral and sea snakes)"}
VENOMOUS_SPIDERS = {47370: "widow spiders", 48137: "recluse spiders"}
# Native or not, the animals most often behind property damage, pet
# attacks, garbage raids or vehicle collisions.
PROBLEM_WILDLIFE = {
    42051: "coyote",
    42158: "deer, elk, moose",
    42134: "wild hogs",
    41663: "raccoon",
    41871: "skunks",
    42652: "opossum",
    41638: "black bear",
    42007: "mountain lion",
    26159: "alligator",
    44540: "rats",
    47075: "armadillo",
}


def _get(session: requests.Session, path: str, params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    throttle(INAT_HOST)
    response = session.get(f"{INAT_API}/{path}", params=params, timeout=config.default_timeout)
    response.raise_for_status()
    return response.json()


def _species_counts(
    session: requests.Session, lat: float, lon: float, config: AppConfig, per_page: int, **filters: Any
) -> list[dict[str, Any]]:
    params = {
        "lat": lat,
        "lng": lon,
        "radius": SEARCH_RADIUS_KM,
        "quality_grade": "research",
        "per_page": per_page,
        **filters,
    }
    return _get(session, "observations/species_counts", params, config).get("results", [])


def _to_species(result: dict[str, Any]) -> Species:
    taxon = result.get("taxon") or {}
    return Species(
        common_name=taxon.get("preferred_common_name") or None,
        scientific_name=str(taxon.get("name", "")),
        observations=int(result.get("count", 0)),
        group=taxon.get("iconic_taxon_name") or None,
        url=f"https://www.inaturalist.org/taxa/{int(taxon['id'])}" if taxon.get("id") else None,
    )


def _in(result: dict[str, Any], taxa: dict[int, str]) -> bool:
    ancestors = set((result.get("taxon") or {}).get("ancestor_ids") or [])
    return bool(ancestors & taxa.keys())


def _state_place(session: requests.Session, lat: float, lon: float, config: AppConfig) -> tuple[int, str] | None:
    """iNaturalist's place for the U.S. state containing the point; 'introduced'
    status is defined per place, so the state is the reference."""
    params = {"nelat": lat, "nelng": lon, "swlat": lat, "swlng": lon, "per_page": 20}
    places = (_get(session, "places/nearby", params, config).get("results") or {}).get("standard") or []
    state = next((p for p in places if p.get("admin_level") == 10), None)
    return (int(state["id"]), str(state["name"])) if state else None


def get_environment(
    session: requests.Session,
    lat: float,
    lon: float,
    area_label: str | None = None,
    config: AppConfig | None = None,
) -> Environment:
    config = config or AppConfig()
    ids = lambda taxa: ",".join(str(i) for i in taxa)  # noqa: E731

    trees = [_to_species(r) for r in _species_counts(session, lat, lon, config, TOP_N, taxon_id=ids(TREE_TAXA))]
    plant_results = _species_counts(session, lat, lon, config, 40, iconic_taxa="Plantae")
    plants = [_to_species(r) for r in plant_results if not _in(r, TREE_TAXA)][:TOP_N]

    fauna_taxa = {**VENOMOUS_SNAKES, **VENOMOUS_SPIDERS, **PROBLEM_WILDLIFE}
    fauna = _species_counts(session, lat, lon, config, 100, taxon_id=ids(fauna_taxa))

    introduced: list[Species] = []
    state_name = None
    state = _state_place(session, lat, lon, config)
    if state:
        place_id, state_name = state
        results = _species_counts(session, lat, lon, config, INTRODUCED_FETCHED, place_id=place_id, introduced="true")
        introduced = [_to_species(r) for r in results]

    return Environment(
        area=area_label or "this area",
        radius_km=SEARCH_RADIUS_KM,
        source=INAT_SOURCE,
        common_plants=plants,
        common_trees=trees,
        venomous_snakes=[_to_species(r) for r in fauna if _in(r, VENOMOUS_SNAKES)],
        venomous_spiders=[_to_species(r) for r in fauna if _in(r, VENOMOUS_SPIDERS)],
        problem_wildlife=[_to_species(r) for r in fauna if _in(r, PROBLEM_WILDLIFE)],
        introduced_species=introduced[:INTRODUCED_SHOWN],
        introduced_reference=state_name,
        introduced_names=[sp.scientific_name for sp in introduced],
    )
