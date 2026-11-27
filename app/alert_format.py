"""Subject and HTML body of the alert emails. Pure functions, no I/O.

The markup is tables with inline styles: email clients (Gmail above all) drop
<style> blocks and do not lay out flexbox or grid.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape

from app.roads import SEARCH_RADIUS_M, Nearest
from app.searches import Operation, RoadWarnings

_PORTAL_NAMES = {
    "zonaprop": "ZonaProp",
    "argenprop": "ArgenProp",
    "mercadolibre": "MercadoLibre",
    "mashogares": "Más Hogares BNA",
}
# First thing in every subject, so rent and sale tell apart in the inbox at a glance.
_OPERATION_TAGS = {Operation.RENT: "[ALQUILER]", Operation.SALE: "[VENTA]"}
_MAX_TITLE_LENGTH = 70

_FONT = "font-family:Arial,Helvetica,sans-serif"
_TEXT = "#1d2433"
_MUTED = "#5b6475"


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
    main_street: Nearest | None
    # The thresholds of the alert the listing is emailed for.
    road_warnings: RoadWarnings


@dataclass(frozen=True)
class RoadLines:
    # One line per road closer than the alert's threshold for it.
    warnings: list[str]
    # The distance to the other roads, or why nothing was measured.
    summary: str | None


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


def _road_distance(label: str, nearest: Nearest | None) -> str:
    if nearest is None:
        return f"sin {label.lower()} a menos de {SEARCH_RADIUS_M / 1000:g} km"
    name = f" ({nearest.name})" if nearest.name else ""
    return f"{label} a ~{nearest.distance_m} m{name}"


def format_road_lines(listing: NewListing) -> RoadLines:
    """Plain text, escaped by the caller. Distances far from any road are shown
    too, so every email tells a listing that is far from roads apart from one that
    was not measured."""
    if not listing.roads_measured:
        return RoadLines(
            warnings=[],
            summary="No se pudo medir la distancia a autopistas, avenidas y calles principales (el aviso no trae ubicación)",
        )
    warnings: list[str] = []
    distances: list[str] = []
    for label, nearest, threshold_m in (
        ("Autopista", listing.motorway, listing.road_warnings.motorway_m),
        ("Avenida", listing.avenue, listing.road_warnings.avenue_m),
        ("Calle principal", listing.main_street, listing.road_warnings.main_street_m),
    ):
        text = _road_distance(label, nearest)
        if nearest is not None and nearest.distance_m <= threshold_m:
            warnings.append(f"⚠ {text}")
        else:
            distances.append(text)
    if not distances:
        return RoadLines(warnings=warnings, summary=None)
    line = " · ".join(distances)
    return RoadLines(warnings=warnings, summary=line[0].upper() + line[1:])


def _paragraph(text: str, style: str) -> str:
    """`text` must already be escaped."""
    return f'<p style="margin:0 0 6px;{_FONT};{style}">{text}</p>'


def _price_html(listing: NewListing) -> str:
    if listing.price is None:
        # Not a price, so neither the large figure nor "/mes".
        return _paragraph(escape(format_price(None, None)), f"font-size:16px;font-weight:bold;color:{_MUTED}")
    per_month = (
        f'<span style="font-size:14px;font-weight:normal;color:{_MUTED}">/mes</span>'
        if listing.operation is Operation.RENT
        else ""
    )
    price = _paragraph(
        f"{escape(format_price(listing.price, listing.currency))}{per_month}",
        "font-size:22px;font-weight:bold;color:#0b6e4f",
    )
    price_per_m2 = format_price_per_m2(listing)
    if not price_per_m2:
        return price
    return price + _paragraph(escape(price_per_m2), f"font-size:13px;color:{_MUTED}")


def _roads_html(listing: NewListing) -> str:
    roads = format_road_lines(listing)
    parts = [
        f'<p style="margin:0 0 4px;padding:6px 10px;background:#fff4e5;border-radius:4px;'
        f'{_FONT};font-size:13px;color:#8a4b00">{escape(warning)}</p>'
        for warning in roads.warnings
    ]
    if roads.summary:
        parts.append(_paragraph(escape(roads.summary), f"font-size:13px;color:{_MUTED}"))
    return "".join(parts)


def _card(listing: NewListing) -> str:
    url = escape(listing.url)
    portal = escape(_PORTAL_NAMES.get(listing.source, listing.source))
    body = [
        _paragraph(portal.upper(), f"font-size:11px;letter-spacing:1px;color:{_MUTED}"),
        _paragraph(
            f'<a href="{url}" style="color:{_TEXT};text-decoration:none">'
            f"{escape(_short_title(listing.title))}</a>",
            "font-size:17px;font-weight:bold",
        ),
        _price_html(listing),
    ]
    if listing.location:
        body.append(_paragraph(escape(listing.location), f"font-size:14px;color:{_TEXT}"))
    details = format_details(listing)
    if details:
        body.append(_paragraph(escape(details), f"font-size:14px;color:{_TEXT}"))
    body.append(f'<div style="margin:10px 0 14px">{_roads_html(listing)}</div>')
    body.append(
        f'<a href="{url}" style="display:inline-block;padding:10px 18px;background:#1d4ed8;'
        f'border-radius:6px;{_FONT};font-size:14px;font-weight:bold;color:#ffffff;'
        f'text-decoration:none">Ver publicación</a>'
    )
    return (
        '<tr><td style="padding:0 0 16px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#ffffff;border:1px solid #e3e6ec;border-radius:8px">'
        f'<tr><td style="padding:20px">{"".join(body)}</td></tr>'
        "</table></td></tr>"
    )


def _page(listings: list[NewListing]) -> str:
    cards = "".join(_card(listing) for listing in listings)
    return (
        f'<div style="margin:0;padding:16px 8px;background:#f2f4f7">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="max-width:600px;margin:0 auto">{cards}</table></div>'
    )


def single_message(alert_id: str, listing: NewListing) -> tuple[str, str]:
    tag = _OPERATION_TAGS[listing.operation]
    return f"{tag} {alert_id}: {_short_title(listing.title)}", _page([listing])


def digest_message(alert_id: str, operation: Operation, listings: list[NewListing]) -> tuple[str, str]:
    """One email for the new listings of one operation, which the subject states."""
    count = len(listings)
    noun = "publicación nueva" if count == 1 else "publicaciones nuevas"
    title = f"{_OPERATION_TAGS[operation]} {alert_id}: {count} {noun}"
    return title, _page(listings)
