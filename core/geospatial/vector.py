"""
Vector ingestion and metadata extraction using GeoPandas.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd

from .models import VectorMetadata


SUPPORTED_VECTOR_EXTENSIONS = {
    ".shp",
    ".geojson",
    ".gpkg",
    ".json",
}


class VectorValidationError(ValueError):
    """Raised for invalid vector inputs."""


def validate_vector_path(path: str | Path) -> Path:
    p = Path(path)

    if not p.exists():
        raise VectorValidationError(f"Vector dataset does not exist: {p}")

    if not p.is_file():
        raise VectorValidationError(f"Vector path is not a file: {p}")

    if p.suffix.lower() not in SUPPORTED_VECTOR_EXTENSIONS:
        raise VectorValidationError(
            f"Unsupported vector format: {p.suffix}"
        )

    return p


def read_vector(path: str | Path) -> gpd.GeoDataFrame:
    p = validate_vector_path(path)
    gdf = gpd.read_file(p)

    if gdf.empty:
        raise VectorValidationError("Vector dataset contains no features.")

    if gdf.geometry.isna().all():
        raise VectorValidationError("Vector dataset contains no valid geometries.")

    return gdf


def read_metadata(path: str | Path) -> VectorMetadata:
    p = validate_vector_path(path)
    gdf = read_vector(p)

    geometry_types = tuple(
        sorted(
            {
                str(value)
                for value in gdf.geometry.geom_type.dropna().unique()
            }
        )
    )

    return VectorMetadata(
        path=str(p.resolve()),
        feature_count=len(gdf),
        geometry_types=geometry_types,
        crs=gdf.crs.to_string() if gdf.crs else None,
        bounds=tuple(float(v) for v in gdf.total_bounds),
    )
