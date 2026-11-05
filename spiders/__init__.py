from collections.abc import Callable, Iterable

from app.models import KnownDetail, Listing, ScrapeResult
from .argenprop import scrape_argenprop
from .mercadolibre import scrape_mercadolibre
from .zonaprop import scrape_zonaprop


ScraperFunc = Callable[..., ScrapeResult]


def _complete(scraper: Callable[..., list[Listing]]) -> ScraperFunc:
	"""Spiders that always read every listing in full have nothing deferred."""
	def scrape(*args, **kwargs) -> ScrapeResult:
		return ScrapeResult(scraper(*args, **kwargs))
	return scrape


_SCRAPERS: dict[str, ScraperFunc] = {
	"mercadolibre": _complete(scrape_mercadolibre),
	"argenprop": scrape_argenprop,
	"zonaprop": _complete(scrape_zonaprop),
}


def scrape_source(
	source: str,
	start_urls: Iterable[str],
	max_pages: int = 3,
	expected_names: list[str] | None = None,
	known: dict[str, KnownDetail] | None = None,
	stop_at_known: bool = False,
) -> ScrapeResult:
	"""Ejecuta el scraper de la fuente pedida.

	`expected_names` solo lo entienden los spiders con constructor de URL (zonaprop,
	argenprop): verifican que la pagina de resultados nombre esos barrios.
	`known` y `stop_at_known` solo los entiende argenprop: no pide el detalle de lo que ya
	conoce, y con `stop_at_known` deja de paginar en la primera pagina sin nada nuevo.
	"""
	normalized = source.strip().lower()

	scraper_func = _SCRAPERS.get(normalized)
	if not scraper_func:
		supported = ", ".join(sorted(_SCRAPERS.keys()))
		raise ValueError(f"Fuente no soportada: '{source}'. Soportadas: [{supported}]")

	options: dict[str, object] = {}
	if expected_names:
		options["expected_names"] = expected_names
	if known is not None:
		options["known"] = known
		options["stop_at_known"] = stop_at_known
	return scraper_func(start_urls, max_pages=max_pages, **options)


__all__ = ["scrape_source"]
