"""
Satellite raster layer abstraction.

The module intentionally does not fabricate satellite observations.
It validates and describes real raster inputs supplied by the user or
an upstream remote-sensing acquisition process.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import rasterio

from .models import SatelliteLayer


class SatelliteDataError(ValueError):
    """Raised for invalid satellite inputs."""


SUPPORTED_SATELLITE_EXTENSIONS = {
    ".tif",
    ".tiff",
    ".vrt",
    ".img",
}


def inspect_satellite_layer(
    path: str | Path,
    *,
    layer_id: str | None = None,
    sensor: str | None = None,
    band: str | None = None,
    acquisition_date: str | None = None,
    resolution_m: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> SatelliteLayer:
    p = Path(path)

    if not p.exists() or not p.is_file():
        raise SatelliteDataError(f"Satellite raster does not exist: {p}")

    if p.suffix.lower() not in SUPPORTED_SATELLITE_EXTENSIONS:
        raise SatelliteDataError(
            f"Unsupported satellite raster format: {p.suffix}"
        )

    with rasterio.open(p) as src:
        if src.count < 1:
            raise SatelliteDataError("Satellite raster contains no bands.")

        detected_resolution = float(
            (abs(src.res[0]) + abs(src.res[1])) / 2
        )

        raster_metadata = {
            "width": src.width,
            "height": src.height,
            "bands": src.count,
            "dtype": src.dtypes[0],
            "crs": src.crs.to_string() if src.crs else None,
            "bounds": [
                src.bounds.left,
                src.bounds.bottom,
                src.bounds.right,
                src.bounds.top,
            ],
            "transform": tuple(src.transform),
        }

    merged_metadata = {
        **raster_metadata,
        **(metadata or {}),
    }

    return SatelliteLayer(
        layer_id=layer_id or p.stem,
        path=str(p.resolve()),
        sensor=sensor,
        band=band,
        acquisition_date=acquisition_date,
        resolution_m=(
            resolution_m
            if resolution_m is not None
            else detected_resolution
        ),
        metadata=merged_metadata,
    )


def validate_satellite_stack(paths: list[str | Path]) -> list[SatelliteLayer]:
    if not paths:
        raise SatelliteDataError("At least one satellite layer is required.")

    return [
        inspect_satellite_layer(path, layer_id=Path(path).stem)
        for path in paths
    ]
