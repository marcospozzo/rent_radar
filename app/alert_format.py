"""Subject and body of the alert emails. Pure functions, no I/O."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.searches import Operation

_PORTAL_NAMES = {"zonaprop": "ZonaProp", "argenprop": "ArgenProp", "mercadolibre": "MercadoLibre"}
# First thing in every subject, so rent and sale tell apart in the inbox at a glance.
_OPERATION_TAGS = {Operation.RENT: "[ALQUILER]", Operation.SALE: "[VENTA]"}
_MAX_TITLE_LENGTH = 70


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


def _block(listing: NewListing) -> str:
    per_month = "/mes" if listing.operation is Operation.RENT else ""
    lines = [
        f"**{_escape(_short_title(listing.title))}**",
        f"{format_price(listing.price, listing.currency)}{per_month} · {_PORTAL_NAMES.get(listing.source, listing.source)}",
    ]
    if listing.location:
        lines.append(_escape(listing.location))
    details = format_details(listing)
    if details:
        lines.append(details)
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
