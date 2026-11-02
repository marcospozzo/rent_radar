"""Builds each portal's search URL from a search definition.

The portals do not document their URL rules; the ones below were checked
against the live sites. A wrong URL does not fail, it searches somewhere else:
ZonaProp, for one, silently drops the neighborhood and returns all of Argentina
when the price segment does not follow the rooms segment. Callers should
therefore check the heading of the first results page before trusting it.
"""
from __future__ import annotations

from app.searches import Neighborhood, Operation, Portal, Search, SearchConfigError

_PROPERTY_TYPE_ORDER = ("casa", "departamento", "ph")
_TYPE_WORDS = {"casa": "casas", "departamento": "departamentos", "ph": "ph"}
_OPERATION_WORDS = {Operation.RENT: "alquiler", Operation.SALE: "venta"}
_CURRENCY_WORDS = {"ARS": "pesos", "USD": "dolares"}

# ArgenProp has no room count above "5 or more".
_ARGENPROP_TOP_ROOMS = 5


def _types_in_canonical_order(search: Search) -> list[str]:
    return [kind for kind in _PROPERTY_TYPE_ORDER if kind in search.property_types]


def build_zonaprop_url(search: Search, neighborhoods: dict[str, Neighborhood]) -> str:
    parts = [
        "-".join(_TYPE_WORDS[kind] for kind in _types_in_canonical_order(search)),
        _OPERATION_WORDS[search.operation],
        "-".join(neighborhoods[key].zonaprop for key in search.neighborhoods),
    ]
    # "mas-de-N" means N or more; "desde-N" alone means exactly N. The rooms
    # segment must come before the price one or the neighborhood is dropped,
    # and a search always has a minimum, so it is always present.
    if search.rooms.max is None:
        parts.append(f"mas-de-{search.rooms.min}-ambientes")
    else:
        parts.append(f"desde-{search.rooms.min}-hasta-{search.rooms.max}-ambientes")
    if search.min_garage:
        parts.append(f"mas-de-{search.min_garage}-garage")
    if search.min_area_m2:
        parts.append(f"mas-{search.min_area_m2}-m2-cubiertos")
    if search.price.max:
        parts.append(f"menos-{search.price.max}-{_CURRENCY_WORDS[search.price.currency]}")
    parts.append("orden-publicado-descendente")
    return f"https://www.zonaprop.com.ar/{'-'.join(parts)}.html"


def _argenprop_rooms_segment(search: Search) -> str:
    lowest = min(search.rooms.min, _ARGENPROP_TOP_ROOMS)
    highest = _ARGENPROP_TOP_ROOMS if search.rooms.max is None else min(search.rooms.max, _ARGENPROP_TOP_ROOMS)
    options = [
        f"{count}-ambientes" if count < _ARGENPROP_TOP_ROOMS else f"{_ARGENPROP_TOP_ROOMS}-o-mas-ambientes"
        for count in range(lowest, highest + 1)
    ]
    return "-o-".join(options)


def build_argenprop_url(search: Search, neighborhoods: dict[str, Neighborhood]) -> str:
    segments = [
        "-o-".join(_TYPE_WORDS[kind] for kind in _types_in_canonical_order(search)),
        _OPERATION_WORDS[search.operation],
        "-o-".join(neighborhoods[key].argenprop for key in search.neighborhoods),
        _argenprop_rooms_segment(search),
    ]
    if search.price.max:
        segments.append(f"{_CURRENCY_WORDS[search.price.currency]}-hasta-{search.price.max}")
    query = []
    if search.min_garage:
        # Checked only for one garage or more.
        query.append(f"{search.min_garage}-o-mas-cocheras")
    query.append("orden-masnuevos-descendente")
    return f"https://www.argenprop.com/{'/'.join(segments)}?{'&'.join(query)}"


def build_portal_urls(portal: Portal, search: Search, neighborhoods: dict[str, Neighborhood]) -> list[str]:
    """URLs to scrape for one portal: the ones written in the search, else generated."""
    configured = search.portals[portal].urls
    if configured:
        return configured
    if portal == "zonaprop":
        return [build_zonaprop_url(search, neighborhoods)]
    if portal == "argenprop":
        return [build_argenprop_url(search, neighborhoods)]
    raise SearchConfigError(
        f"Search '{search.id}': {portal} has no URL builder yet; "
        f"set portals.{portal}.urls in alerts.yaml"
    )
