from collections.abc import Callable, Iterable

from app.models import Listing
from .argenprop import scrape_argenprop
from .mercadolibre import scrape_mercadolibre
from .zonaprop import scrape_zonaprop


ScraperFunc = Callable[..., list[Listing]]

_SCRAPERS: dict[str, ScraperFunc] = {
	"mercadolibre": scrape_mercadolibre,
	"argenprop": scrape_argenprop,
	"zonaprop": scrape_zonaprop,
}


def scrape_source(
	source: str,
	start_urls: Iterable[str],
	max_pages: int = 3,
	expected_names: list[str] | None = None,
) -> list[Listing]:
	"""Ejecuta el scraper de la fuente pedida.

	`expected_names` solo lo entienden los spiders con constructor de URL (zonaprop,
	argenprop): verifican que la pagina de resultados nombre esos barrios.
	"""
	normalized = source.strip().lower()

	scraper_func = _SCRAPERS.get(normalized)
	if not scraper_func:
		supported = ", ".join(sorted(_SCRAPERS.keys()))
		raise ValueError(f"Fuente no soportada: '{source}'. Soportadas: [{supported}]")

	if expected_names:
		return scraper_func(start_urls, max_pages=max_pages, expected_names=expected_names)
	return scraper_func(start_urls, max_pages=max_pages)


__all__ = ["scrape_source"]
