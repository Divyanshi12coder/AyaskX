"""
AyaskX geospatial data models.

These models describe validated geospatial inputs and derived terrain
information without coupling the GIS layer to the ML pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RasterMetadata:
    path: str
    width: int
    height: int
    bands: int
    dtype: str
    crs: str | None
    bounds: tuple[float, float, float, float]
    resolution: tuple[float, float]
    nodata: float | int | None
    driver: str


@dataclass(frozen=True)
class VectorMetadata:
    path: str
    feature_count: int
    geometry_types: tuple[str, ...]
    crs: str | None
    bounds: tuple[float, float, float, float]


@dataclass(frozen=True)
class TerrainSummary:
    elevation_min: float
    elevation_max: float
    elevation_mean: float
    elevation_std: float
    slope_min: float
    slope_max: float
    slope_mean: float
    valid_cells: int


@dataclass(frozen=True)
class SatelliteLayer:
    layer_id: str
    path: str
    sensor: str | None
    band: str | None
    acquisition_date: str | None
    resolution_m: float | None
    metadata: dict[str, Any] = field(default_factory=dict)
