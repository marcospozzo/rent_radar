from collections.abc import Callable, Iterable

from app.models import KnownDetail, Listing, ScrapeResult
from .argenprop import scrape_argenprop
from .mashogares import scrape_mashogares
from .mercadolibre import scrape_mercadolibre
from .zonaprop import scrape_zonaprop


ScraperFunc = Callable[..., ScrapeResult]


def _complete(scraper: Callable[..., list[Listing]]) -> ScraperFunc:
	"""Spiders that read every listing they ask for have nothing deferred."""
	def scrape(*args, **kwargs) -> ScrapeResult:
		return ScrapeResult(scraper(*args, **kwargs))
	return scrape


_SCRAPERS: dict[str, ScraperFunc] = {
	"mercadolibre": _complete(scrape_mercadolibre),
	"argenprop": scrape_argenprop,
	"zonaprop": _complete(scrape_zonaprop),
	"mashogares": _complete(scrape_mashogares),
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
	argenprop, mashogares): los dos primeros verifican que la pagina de resultados
	nombre esos barrios; mashogares se queda solo con los avisos de esas localidades.
	`known` lo entienden argenprop y mercadolibre: no piden el detalle de lo que ya conocen.
	`stop_at_known` solo argenprop: deja de paginar en la primera pagina sin nada nuevo
	(mercadolibre no ordena por fecha, asi que no puede cortar).
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
		if stop_at_known:
			options["stop_at_known"] = True
	return scraper_func(start_urls, max_pages=max_pages, **options)


__all__ = ["scrape_source"]
