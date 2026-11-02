from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class Listing(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source: str
    listing_id: str
    url: str
    title: str
    price: int | None = None
    currency: str | None = None
    expenses: int | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    rooms: int | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    surface_m2: int | None = None
    published_at: datetime | None = None
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    seller: str | None = None
    specifications: list[str] = Field(default_factory=list)

    def to_snapshot_row(self, run_id: str) -> dict[str, Any]:
        return {
            "id_ejecucion": run_id,
            "fuente": self.source,
            "id_publicacion": self.listing_id,
            "url": self.url,
            "titulo": self.title,
            "precio": self.price,
            "moneda": self.currency,
            "expensas": self.expenses,
            "ubicacion": self.location,
            "latitud": self.latitude,
            "longitud": self.longitude,
            "ambientes": self.rooms,
            "dormitorios": self.bedrooms,
            "banos": self.bathrooms,
            "superficie_m2": self.surface_m2,
            "publicado_en": self.published_at,
            "fecha_scraping": self.scraped_at,
            "vendedor": self.seller,
            "especificaciones": self.specifications,
        }


class PipelineRun(BaseModel):
    source: str
    status: str = "running"
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    listings_found: int = 0
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    search_id: str | None = None

    def to_run_row(self) -> dict[str, Any]:
        return {
            "id_ejecucion": self.run_id,
            "id_busqueda": self.search_id,
            "fuente": self.source,
            "estado": self.status,
            "iniciado_en": self.started_at,
            "finalizado_en": self.finished_at,
            "total_publicaciones": self.listings_found,
        }
