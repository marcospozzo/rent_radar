"""Subject and body of the alert emails. Pure functions, no I/O."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.roads import Nearest
from app.searches import Operation

_PORTAL_NAMES = {
    "zonaprop": "ZonaProp",
    "argenprop": "ArgenProp",
    "mercadolibre": "MercadoLibre",
    "mashogares": "Más Hogares BNA",
}
# First thing in every subject, so rent and sale tell apart in the inbox at a glance.
_OPERATION_TAGS = {Operation.RENT: "[ALQUILER]", Operation.SALE: "[VENTA]"}
_MAX_TITLE_LENGTH = 70
# Closer than this the email warns. First guesses, to tune against
# silver.cercania_vias: a motorway is heard from a few blocks away, while an
# avenue matters when the listing faces it, not when it is on the next block.
MOTORWAY_WARNING_M = 300
AVENUE_WARNING_M = 60


@dataclass(frozen=True)
class NewListing:
    operation: Operation
    source: str
    title: str
    url: str
    price: float | None
    currency: str | None
    location: str | None
    rooms: int | None
    area_m2: float | None
    garage: int | None
    age_years: int | None
    roads_measured: bool
    motorway: Nearest | None
    avenue: Nearest | None


def _escape(text: str) -> str:
    # Titles come from the portals; an unescaped * or [ would mangle the email.
    return re.sub(r"([\\`*_\[\]])", r"\\\1", text)


def _short_title(title: str) -> str:
    return title if len(title) <= _MAX_TITLE_LENGTH else title[: _MAX_TITLE_LENGTH - 1] + "…"


def format_price(price: float | None, currency: str | None) -> str:
    if price is None:
        return "Precio a consultar"
    amount = f"{int(price):,}".replace(",", ".")
    return f"USD {amount}" if currency == "USD" else f"$ {amount}"


def format_price_per_m2(listing: NewListing) -> str | None:
    """None when the listing has no price or area to divide."""
    if not listing.price or not listing.area_m2:
        return None
    return f"{format_price(listing.price / listing.area_m2, listing.currency)}/m²"


def format_details(listing: NewListing) -> str:
    parts = []
    if listing.rooms is not None:
        parts.append(f"{listing.rooms} amb")
    if listing.area_m2 is not None:
        parts.append(f"{int(listing.area_m2)} m²")
    if listing.garage:
        parts.append(f"{listing.garage} coch")
    if listing.age_years is not None:
        parts.append("a estrenar" if listing.age_years == 0 else f"{listing.age_years} años")
    return " · ".join(parts)


def _road_warning(label: str, nearest: Nearest | None, threshold_m: int) -> str | None:
    if nearest is None or nearest.distance_m > threshold_m:
        return None
    name = f" ({_escape(nearest.name)})" if nearest.name else ""
    return f"⚠ {label} a ~{nearest.distance_m} m{name}"


def format_road_warnings(listing: NewListing) -> list[str]:
    if not listing.roads_measured:
        return ["No se pudo medir la distancia a autopistas y avenidas (el aviso no trae ubicación)"]
    warnings = [
        _road_warning("Autopista", listing.motorway, MOTORWAY_WARNING_M),
        _road_warning("Avenida", listing.avenue, AVENUE_WARNING_M),
    ]
    return [warning for warning in warnings if warning]


def _block(listing: NewListing) -> str:
    per_month = "/mes" if listing.operation is Operation.RENT else ""
    price_parts = [f"{format_price(listing.price, listing.currency)}{per_month}"]
    price_per_m2 = format_price_per_m2(listing)
    if price_per_m2:
        price_parts.append(price_per_m2)
    price_parts.append(_PORTAL_NAMES.get(listing.source, listing.source))
    lines = [
        f"**{_escape(_short_title(listing.title))}**",
        " · ".join(price_parts),
    ]
    if listing.location:
        lines.append(_escape(listing.location))
    details = format_details(listing)
    if details:
        lines.append(details)
    lines.extend(format_road_warnings(listing))
    lines.append(f"[Ver publicación]({listing.url})")
    # Two trailing spaces are Markdown's line break.
    return "  \n".join(lines)


def single_message(alert_id: str, listing: NewListing) -> tuple[str, str]:
    tag = _OPERATION_TAGS[listing.operation]
    return f"{tag} {alert_id}: {_short_title(listing.title)}", _block(listing)


def digest_message(alert_id: str, operation: Operation, listings: list[NewListing]) -> tuple[str, str]:
    """One email for the new listings of one operation, which the subject states."""
    count = len(listings)
    noun = "publicación nueva" if count == 1 else "publicaciones nuevas"
    title = f"{_OPERATION_TAGS[operation]} {alert_id}: {count} {noun}"
    return title, "\n\n".join(_block(listing) for listing in listings)
