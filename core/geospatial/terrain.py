"""
Terrain analysis from DEM rasters.

Derives elevation and slope statistics while preserving nodata cells.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine

from .models import TerrainSummary


class TerrainError(ValueError):
    """Raised when terrain analysis cannot be performed."""


def _slope_degrees(
    elevation: np.ndarray,
    transform: Affine,
) -> np.ndarray:
    x_res = abs(transform.a)
    y_res = abs(transform.e)

    if x_res <= 0 or y_res <= 0:
        raise TerrainError("DEM has invalid spatial resolution.")

    filled = np.asarray(elevation, dtype=float)

    dz_dy, dz_dx = np.gradient(filled, y_res, x_res)

    gradient = np.sqrt(dz_dx**2 + dz_dy**2)

    return np.degrees(np.arctan(gradient))


def terrain_summary(path: str | Path, band: int = 1) -> TerrainSummary:
    p = Path(path)

    if not p.exists():
        raise TerrainError(f"DEM does not exist: {p}")

    with rasterio.open(p) as src:
        if src.count < band or band < 1:
            raise TerrainError(f"Invalid DEM band: {band}")

        elevation = src.read(band, masked=True)

        if elevation.mask is np.ma.nomask:
            mask = np.zeros(elevation.shape, dtype=bool)
        else:
            mask = np.asarray(elevation.mask, dtype=bool)

        values = np.asarray(elevation.data, dtype=float)
        values[mask] = np.nan

        valid = np.isfinite(values)

        if not np.any(valid):
            raise TerrainError("DEM contains no valid elevation cells.")

        slope = _slope_degrees(values, src.transform)
        slope[~valid] = np.nan

        elev_values = values[valid]
        slope_values = slope[np.isfinite(slope)]

    return TerrainSummary(
        elevation_min=float(np.min(elev_values)),
        elevation_max=float(np.max(elev_values)),
        elevation_mean=float(np.mean(elev_values)),
        elevation_std=float(np.std(elev_values)),
        slope_min=float(np.min(slope_values)),
        slope_max=float(np.max(slope_values)),
        slope_mean=float(np.mean(slope_values)),
        valid_cells=int(elev_values.size),
    )


def calculate_slope(path: str | Path, band: int = 1) -> np.ndarray:
    p = Path(path)

    with rasterio.open(p) as src:
        elevation = src.read(band, masked=True)

        values = elevation.filled(np.nan).astype(float)

        return _slope_degrees(values, src.transform)
