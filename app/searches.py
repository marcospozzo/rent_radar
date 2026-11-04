"""Alert definitions: what Marc is looking for, loaded from alerts.yaml."""
from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

# Relative to the working directory, which is /app for every job in the image.
ALERTS_FILE = Path(os.environ.get("ALERTS_FILE", "config/alerts.yaml"))
NEIGHBORHOODS_FILE = Path(os.environ.get("NEIGHBORHOODS_FILE", "config/neighborhoods.yaml"))

Portal = Literal["zonaprop", "argenprop", "mercadolibre"]
PropertyType = Literal["casa", "departamento", "ph"]


class SearchConfigError(Exception):
    """The configuration is wrong in a way the message tells how to fix."""


class _Strict(BaseModel):
    # A misspelled key must fail loudly instead of being silently ignored.
    model_config = ConfigDict(extra="forbid")


class Operation(str, Enum):
    RENT = "rent"
    SALE = "sale"


class Delivery(str, Enum):
    DIGEST = "digest"  # one email per cycle with everything new
    EACH = "each"  # one email per listing


class Rooms(_Strict):
    min: int = Field(ge=1)
    max: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _max_not_below_min(self) -> Rooms:
        if self.max is not None and self.max < self.min:
            raise ValueError("rooms.max is lower than rooms.min")
        return self


class Price(_Strict):
    currency: Literal["ARS", "USD"]
    min: int | None = Field(default=None, gt=0)
    max: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _max_not_below_min(self) -> Price:
        if self.min is not None and self.max is not None and self.max < self.min:
            raise ValueError("price.max is lower than price.min")
        return self


class PortalConfig(_Strict):
    max_pages: int = Field(default=20, ge=1)
    urls: list[str] = Field(default_factory=list)


class Search(_Strict):
    """One alert from alerts.yaml: one operation looked up on the portals, which is
    what the pipeline actually runs."""

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    operation: Operation
    delivery: Delivery = Delivery.DIGEST
    active: bool = True
    neighborhoods: list[str] = Field(min_length=1)
    property_types: list[PropertyType] = Field(min_length=1)
    rooms: Rooms
    min_garage: int = Field(default=0, ge=0)
    min_area_m2: int | None = Field(default=None, gt=0)
    price: Price
    portals: dict[Portal, PortalConfig] = Field(min_length=1)

    @field_validator("operation", mode="before")
    @classmethod
    def _one_operation_per_alert(cls, value: object) -> object:
        if value == "both":
            raise ValueError(
                "an alert is either 'rent' or 'sale'; to look for both, write two alerts, "
                "each with its own price"
            )
        return value


class Neighborhood(_Strict):
    name: str
    zonaprop: str
    argenprop: str


class AppriseService(_Strict):
    # The Apprise URL carries a password, so it lives in a file outside the repo
    # and the YAML only points at it.
    url_file: str
    label: str | None = None


class AppriseConfig(_Strict):
    services: list[AppriseService] = Field(min_length=1)


class HealthConfig(_Strict):
    enabled: bool = True


class _AlertsFile(_Strict):
    apprise: AppriseConfig
    health: HealthConfig = Field(default_factory=HealthConfig)
    alerts: list[Search]


class Config(_Strict):
    apprise: AppriseConfig
    health: HealthConfig
    searches: list[Search]


def _read_yaml(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SearchConfigError(f"Cannot read {path}: {exc.strerror}") from exc
    except yaml.YAMLError as exc:
        raise SearchConfigError(f"{path} is not valid YAML: {exc}") from exc


def _describe(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors()
    )


def load_neighborhoods(path: Path = NEIGHBORHOODS_FILE) -> dict[str, Neighborhood]:
    raw = _read_yaml(path)
    if not isinstance(raw, dict):
        raise SearchConfigError(f"{path} must map each neighborhood key to its portal names")
    try:
        return {key: Neighborhood.model_validate(value) for key, value in raw.items()}
    except ValidationError as exc:
        raise SearchConfigError(f"{path}: {_describe(exc)}") from exc


def load_config(
    alerts_path: Path = ALERTS_FILE,
    neighborhoods_path: Path = NEIGHBORHOODS_FILE,
) -> Config:
    if not alerts_path.exists():
        # alerts.yaml is personal and git ignores it, so a fresh clone has none.
        raise SearchConfigError(
            f"{alerts_path} does not exist: copy {alerts_path.with_name('alerts.example.yaml')} "
            f"to {alerts_path} and edit it"
        )
    try:
        parsed = _AlertsFile.model_validate(_read_yaml(alerts_path))
    except ValidationError as exc:
        raise SearchConfigError(f"{alerts_path}: {_describe(exc)}") from exc
    known_neighborhoods = load_neighborhoods(neighborhoods_path)
    seen_ids: set[str] = set()
    for search in parsed.alerts:
        for neighborhood in search.neighborhoods:
            if neighborhood not in known_neighborhoods:
                raise SearchConfigError(
                    f"{alerts_path}: alert '{search.id}' uses neighborhood '{neighborhood}', "
                    f"which is not in {neighborhoods_path} "
                    f"(known: {', '.join(sorted(known_neighborhoods))})"
                )
        if search.id in seen_ids:
            raise SearchConfigError(f"{alerts_path}: id '{search.id}' appears more than once")
        seen_ids.add(search.id)
    return Config(apprise=parsed.apprise, health=parsed.health, searches=parsed.alerts)
