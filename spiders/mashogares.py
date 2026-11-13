"""Spider for Más Hogares BNA (mashogaresconbna.com.ar), a sale-only portal.

Its pages are rendered in the browser from a public JSON API, so this reads the API
the pages read: every result already carries price, size, coordinates and the
seller, and no detail page is needed.

Two behaviours of that API were found by testing it against the live portal:
- A place is matched by `provincia` and `localidad` name. Without the province the
  filter is ignored and the answer is all of Argentina, and the match is by
  substring (asking for "Florida" also returns "Florida Oeste" and "Villa La
  Florida"), so results are cut to the exact localities asked for.
- A filter given twice keeps only the last value, so the URL builder asks for one
  property type per URL instead of several.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

from app.models import Listing
from spiders.headings import WrongSearchPageError

logger = logging.getLogger(__name__)

SITE = "https://mashogaresconbna.com.ar"


@dataclass(slots=True)
class SpiderConfig:
    request_timeout: int = 20
    max_pages: int = 3
    # Seconds before every request, to keep the pace of a person browsing.
    request_delay: float = 1.0


class MashogaresSpider:
    def __init__(self, config: SpiderConfig | None = None, expected_names: list[str] | None = None):
        self.config = config or SpiderConfig()
        self.expected_names = {name.casefold() for name in expected_names or []}
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
            }
        )

    def scrape(self, start_urls: Iterable[str]) -> list[Listing]:
        results: list[Listing] = []
        for start_url in start_urls:
            logger.info("Iniciando scrape | url=%s", start_url)
            before = len(results)
            for item in self._iter_items(start_url):
                locality = str(item.get("localidad", "")).casefold()
                self._check_locality(locality)
                if self.expected_names and locality not in self.expected_names:
                    continue
                listing = _parse_listing(item)
                if listing is not None:
                    results.append(listing)
            logger.info("Scrape completado | url=%s | publicaciones=%d", start_url, len(results) - before)
        if not results:
            logger.warning("Se obtuvieron 0 publicaciones en total.")
        return results

    def _iter_items(self, start_url: str) -> Iterable[dict[str, Any]]:
        for page in range(1, self.config.max_pages + 1):
            body = self._get_page(start_url, page)
            if body is None:
                return
            items = body.get("data") or []
            logger.info("Pagina %d: %d publicaciones encontradas", page, len(items))
            yield from items
            if not body.get("nextPage"):
                return

    def _get_page(self, start_url: str, page: int) -> dict[str, Any] | None:
        parts = urlparse(start_url)
        query = parse_qs(parts.query)
        query["page"] = [str(page)]
        url = urlunparse(parts._replace(query=urlencode(query, doseq=True)))
        time.sleep(self.config.request_delay)
        try:
            response = self.session.get(url, timeout=self.config.request_timeout)
            response.raise_for_status()
            return response.json()["response"]
        except (requests.RequestException, ValueError, KeyError) as exc:
            # The API answers a page past the last one with a body that has no
            # "response"; the loop stops at `nextPage` before asking for it.
            logger.warning("No se pudo leer la pagina %d (%s): %s", page, type(exc).__name__, exc)
            return None

    def _check_locality(self, locality: str) -> None:
        # The portal matches a place by substring, so every honest answer names a
        # locality that contains one asked for. Anything else means the filter was
        # ignored, which would send listings from all over the country to the alerts.
        # The province is not checked: a few listings carry "Provincia de Buenos
        # Aires" where the rest say "Buenos Aires".
        if self.expected_names and not any(name in locality for name in self.expected_names):
            raise WrongSearchPageError(
                f"Mas Hogares BNA devolvio un aviso de {locality!r}, que no corresponde a ninguno "
                f"de los barrios pedidos ({', '.join(sorted(self.expected_names))}): ignoro el filtro de ubicacion"
            )


def _number(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _coordinate(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _specifications(item: dict[str, Any]) -> list[str]:
    # Written the way MercadoLibre's are, which silver.publicaciones already parses.
    entries = (
        ("Superficie cubierta: {} m²", item.get("superficieCubierta")),
        ("Superficie total: {} m²", item.get("superficieTotal")),
        ("Cocheras: {}", item.get("cocheras")),
        ("Antigüedad: {} años", item.get("antiguedadAnos")),
    )
    return [template.format(_number(value)) for template, value in entries if _number(value) is not None]


def _expenses(item: dict[str, Any]) -> int | None:
    # Expenses are compared in pesos downstream. The portal states their currency,
    # and some are entered in dollars as if they were pesos (210000 USD of expenses
    # on a 72000 USD flat), so only those declared in pesos are trusted.
    if item.get("monedaExpensas") != "ARS":
        return None
    expenses = _number(item.get("expensas"))
    return expenses if expenses and expenses > 0 else None


def _parse_listing(item: dict[str, Any]) -> Listing | None:
    if item.get("eliminado") or not item.get("publicado"):
        return None
    listing_id = item.get("id")
    if listing_id is None:
        return None
    street = " ".join(part for part in (item.get("calle"), item.get("altura")) if part)
    location = ", ".join(part for part in (street, item.get("localidad")) if part)
    title = (item.get("titulo") or "").strip() or f"{item.get('tipo', 'Propiedad')} en {item.get('localidad', '')}".strip()
    created = item.get("fechaCreacion")
    return Listing(
        source="mashogares",
        listing_id=str(listing_id),
        url=f"{SITE}/propiedad/{listing_id}",
        title=title,
        price=_number(item.get("precio")),
        currency=item.get("moneda"),
        expenses=_expenses(item),
        location=location or None,
        latitude=_coordinate(item.get("latitud")),
        longitude=_coordinate(item.get("longitud")),
        rooms=_number(item.get("ambientes")),
        bedrooms=_number(item.get("dormitorios")),
        bathrooms=_number(item.get("banos")),
        surface_m2=_number(item.get("superficieCubierta")) or _number(item.get("superficieTotal")),
        published_at=datetime.fromisoformat(created.replace("Z", "+00:00")) if created else None,
        seller=(item.get("inmobiliaria") or {}).get("nombreComercial"),
        specifications=_specifications(item),
    )


def scrape_mashogares(
    start_urls: Iterable[str],
    max_pages: int = 3,
    expected_names: list[str] | None = None,
) -> list[Listing]:
    spider = MashogaresSpider(config=SpiderConfig(max_pages=max_pages), expected_names=expected_names)
    return spider.scrape(start_urls)
