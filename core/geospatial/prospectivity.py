"""
Spatial feature preparation for manganese prospectivity modelling.

This module prepares aligned numerical layers. It does not claim that
a prospectivity prediction exists until an actual trained model produces it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling


class ProspectivityError(ValueError):
    """Raised when spatial feature preparation fails."""


def align_raster(
    source_path: str | Path,
    reference_path: str | Path,
    band: int = 1,
    resampling: Resampling = Resampling.bilinear,
) -> np.ndarray:
    source_path = Path(source_path)
    reference_path = Path(reference_path)

    with rasterio.open(reference_path) as ref:
        destination = np.full(
            (ref.height, ref.width),
            np.nan,
            dtype=np.float32,
        )

        with rasterio.open(source_path) as src:
            if band < 1 or band > src.count:
                raise ProspectivityError(
                    f"Band {band} unavailable in {source_path}"
                )

            reproject(
                source=src.read(band),
                destination=destination,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=ref.transform,
                dst_crs=ref.crs,
                resampling=resampling,
                src_nodata=src.nodata,
                dst_nodata=np.nan,
            )

    return destination


def stack_layers(
    reference_path: str | Path,
    layers: list[tuple[str | Path, int]],
) -> tuple[np.ndarray, list[str]]:
    if not layers:
        raise ProspectivityError("No prospectivity layers supplied.")

    arrays: list[np.ndarray] = []
    names: list[str] = []

    for path, band in layers:
        arrays.append(
            align_raster(
                source_path=path,
                reference_path=reference_path,
                band=band,
            )
        )
        names.append(f"{Path(path).stem}:band_{band}")

    return np.stack(arrays, axis=-1), names


def valid_pixel_mask(feature_stack: np.ndarray) -> np.ndarray:
    if feature_stack.ndim != 3:
        raise ProspectivityError(
            "Feature stack must have shape (height, width, features)."
        )

    return np.all(np.isfinite(feature_stack), axis=-1)
