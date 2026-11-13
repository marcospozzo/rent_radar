"""Builds each portal's search URL from a search definition.

The portals do not document their URL rules; the ones below were checked
against the live sites. A wrong URL does not fail, it searches somewhere else:
ZonaProp, for one, silently drops the neighborhood and returns all of Argentina
when the price segment does not follow the rooms segment. Callers should
therefore check the heading of the first results page before trusting it.
"""
from __future__ import annotations

from app.searches import Neighborhood, Operation, Portal, Search

_PROPERTY_TYPE_ORDER = ("casa", "departamento", "ph")
_TYPE_WORDS = {"casa": "casas", "departamento": "departamentos", "ph": "ph"}
_OPERATION_WORDS = {Operation.RENT: "alquiler", Operation.SALE: "venta"}
_CURRENCY_WORDS = {"ARS": "pesos", "USD": "dolares"}
_MERCADOLIBRE_TYPE_WORDS = {"casa": "casas", "departamento": "departamentos", "ph": "ph"}

# ArgenProp has no room count above "5 or more".
_ARGENPROP_TOP_ROOMS = 5

# ZonaProp's room filter tops out at 5; any larger "hasta" is read as 5.
_ZONAPROP_TOP_ROOMS = 5
_ZONAPROP_ROOMS_CEILING = 10


def _types_in_canonical_order(search: Search) -> list[str]:
    return [kind for kind in _PROPERTY_TYPE_ORDER if kind in search.property_types]


def _zonaprop_rooms_segment(search: Search) -> str:
    rooms = search.rooms
    if rooms.max is not None:
        return f"desde-{rooms.min}-hasta-{rooms.max}-ambientes"
    # "mas-de-N" means N or more; "desde-N" alone means exactly N. But "mas-de-N"
    # together with a price cap in dollars makes ZonaProp drop part of the
    # location: it lost Saavedra from a three-neighborhood search, and with
    # Saavedra alone it searched all of Argentina. A minimum in dollars does the
    # same, and prices in pesos are fine. Written as a range the dollar price keeps
    # every neighborhood, at the cost of listings with six or more rooms, which a
    # range up to "5" does not return.
    has_dollar_price = search.price.currency == "USD" and (search.price.min or search.price.max)
    if has_dollar_price and rooms.min <= _ZONAPROP_TOP_ROOMS:
        return f"desde-{rooms.min}-hasta-{_ZONAPROP_ROOMS_CEILING}-ambientes"
    return f"mas-de-{rooms.min}-ambientes"


def _zonaprop_price_segment(search: Search) -> str | None:
    price = search.price
    currency = _CURRENCY_WORDS[price.currency]
    if price.min and price.max:
        return f"{price.min}-{price.max}-{currency}"
    if price.min:
        return f"mas-{price.min}-{currency}"
    if price.max:
        return f"menos-{price.max}-{currency}"
    return None


def build_zonaprop_url(search: Search, neighborhoods: dict[str, Neighborhood]) -> str:
    parts = [
        "-".join(_TYPE_WORDS[kind] for kind in _types_in_canonical_order(search)),
        _OPERATION_WORDS[search.operation],
        "-".join(neighborhoods[key].zonaprop for key in search.neighborhoods),
        # The rooms segment must come before the price one or the neighborhood is
        # dropped, and a search always has a minimum, so it is always present.
        _zonaprop_rooms_segment(search),
    ]
    if search.min_garage:
        parts.append(f"mas-de-{search.min_garage}-garage")
    if search.min_area_m2:
        parts.append(f"mas-{search.min_area_m2}-m2-cubiertos")
    price_segment = _zonaprop_price_segment(search)
    if price_segment:
        parts.append(price_segment)
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


def _argenprop_price_segment(search: Search) -> str | None:
    price = search.price
    currency = _CURRENCY_WORDS[price.currency]
    if price.min and price.max:
        return f"{currency}-{price.min}-{price.max}"
    if price.min:
        return f"{currency}-desde-{price.min}"
    if price.max:
        return f"{currency}-hasta-{price.max}"
    return None


def build_argenprop_url(search: Search, neighborhoods: dict[str, Neighborhood]) -> str:
    segments = [
        "-o-".join(_TYPE_WORDS[kind] for kind in _types_in_canonical_order(search)),
        _OPERATION_WORDS[search.operation],
        "-o-".join(neighborhoods[key].argenprop for key in search.neighborhoods),
        _argenprop_rooms_segment(search),
    ]
    price_segment = _argenprop_price_segment(search)
    if price_segment:
        segments.append(price_segment)
    query = []
    if search.min_garage:
        # Checked only for one garage or more.
        query.append(f"{search.min_garage}-o-mas-cocheras")
    query.append("orden-masnuevos-descendente")
    return f"https://www.argenprop.com/{'/'.join(segments)}?{'&'.join(query)}"


def _mercadolibre_filters(search: Search) -> str:
    # Filters are appended to the place as "_Name_value". Underscores inside a
    # filter's own name are written "*". The order is the one MercadoLibre itself
    # produces when the filters are applied in its page. No sort order is asked for:
    # "newest first" (_OrderId_AUCTION*STOP) made the CABA URLs fail.
    filters: list[str] = []
    price = search.price
    # A minimum alone has no form that was checked, so it is left to dbt.
    if price.max:
        filters.append(f"_PriceRange_{price.min or 0}{price.currency}-{price.max}{price.currency}")
    # Every URL copied from the page with more than one facet applied has this, and
    # the type and the place already are two; the CABA ones always do.
    filters.append("_NoIndex_True")
    if search.min_garage:
        filters.append(f"_PARKING*LOTS_{search.min_garage}-*")
    if search.min_area_m2:
        # MercadoLibre filters by total area; the covered area is never larger, so
        # this never drops a listing that dbt would keep.
        filters.append(f"_TOTAL*AREA_{search.min_area_m2}m%C2%B2-*")
    return "".join(filters)


def build_mercadolibre_urls(search: Search, neighborhoods: dict[str, Neighborhood]) -> list[str]:
    """A MercadoLibre search covers one property type in one place, so a search is
    one URL for each type and neighborhood."""
    # "mas-de-N-ambientes" means N or more; a maximum is left to dbt. One room or
    # more is every listing, so it needs no filter.
    rooms = f"mas-de-{search.rooms.min}-ambientes/" if search.rooms.min > 1 else ""
    filters = _mercadolibre_filters(search)
    return [
        f"https://inmuebles.mercadolibre.com.ar/{_MERCADOLIBRE_TYPE_WORDS[kind]}/"
        f"{_OPERATION_WORDS[search.operation]}/{rooms}{neighborhoods[key].mercadolibre}{filters}"
        for key in search.neighborhoods
        for kind in _types_in_canonical_order(search)
    ]


def build_portal_urls(portal: Portal, search: Search, neighborhoods: dict[str, Neighborhood]) -> list[str]:
    """URLs to scrape for one portal, generated from the search."""
    if portal == "zonaprop":
        return [build_zonaprop_url(search, neighborhoods)]
    if portal == "argenprop":
        return [build_argenprop_url(search, neighborhoods)]
    return build_mercadolibre_urls(search, neighborhoods)
