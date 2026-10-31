"""Guard against a results page that is not the search we asked for."""
from __future__ import annotations


class WrongSearchPageError(Exception):
    """The portal answered with a page for a different search than requested."""


def missing_names(heading: str, names: list[str]) -> list[str]:
    """The expected neighborhood names that the page heading does not mention."""
    text = heading.casefold()
    return [name for name in names if name.casefold() not in text]
