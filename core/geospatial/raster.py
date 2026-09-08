"""
Raster ingestion and metadata extraction.

Supports GeoTIFF and other formats supported by rasterio.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio

from .models import RasterMetadata


SUPPORTED_RASTER_EXTENSIONS = {
    ".tif",
    ".tiff",
    ".img",
    ".vrt",
}


class RasterValidationError(ValueError):
    """Raised for invalid raster inputs."""


def validate_raster_path(path: str | Path) -> Path:
    p = Path(path)

    if not p.exists():
        raise RasterValidationError(f"Raster does not exist: {p}")

    if not p.is_file():
        raise RasterValidationError(f"Raster path is not a file: {p}")

    if p.suffix.lower() not in SUPPORTED_RASTER_EXTENSIONS:
        raise RasterValidationError(
            f"Unsupported raster format: {p.suffix}"
        )

    return p


def read_metadata(path: str | Path) -> RasterMetadata:
    p = validate_raster_path(path)

    with rasterio.open(p) as src:
        return RasterMetadata(
            path=str(p.resolve()),
            width=src.width,
            height=src.height,
            bands=src.count,
            dtype=str(src.dtypes[0]),
            crs=src.crs.to_string() if src.crs else None,
            bounds=(
                src.bounds.left,
                src.bounds.bottom,
                src.bounds.right,
                src.bounds.top,
            ),
            resolution=src.res,
            nodata=src.nodata,
            driver=src.driver,
        )


def read_band(
    path: str | Path,
    band: int = 1,
    masked: bool = True,
) -> np.ndarray:
    p = validate_raster_path(path)

    with rasterio.open(p) as src:
        if band < 1 or band > src.count:
            raise RasterValidationError(
                f"Band {band} is outside available range 1..{src.count}."
            )

        data = src.read(band, masked=masked)

    return data


def read_all_bands(
    path: str | Path,
    masked: bool = True,
) -> np.ndarray:
    p = validate_raster_path(path)

    with rasterio.open(p) as src:
        return src.read(masked=masked)


def valid_statistics(path: str | Path, band: int = 1) -> dict[str, float | int]:
    data = read_band(path, band=band, masked=True)

    if np.ma.isMaskedArray(data):
        values = data.compressed()
    else:
        values = np.asarray(data).ravel()

    values = values[np.isfinite(values)]

    if values.size == 0:
        raise RasterValidationError("Raster contains no valid numeric cells.")

    return {
        "valid_cells": int(values.size),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
    }
