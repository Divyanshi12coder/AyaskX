"""AyaskX geospatial analysis package."""

from .crs import (
    CRSValidationError,
    are_equivalent,
    crs_string,
    normalize_crs,
    require_same_crs,
)
from .raster import (
    RasterValidationError,
    read_all_bands,
    read_band,
    read_metadata,
    valid_statistics,
)
from .satellite import (
    SatelliteDataError,
    inspect_satellite_layer,
    validate_satellite_stack,
)
from .terrain import TerrainError, calculate_slope, terrain_summary
from .vector import (
    VectorValidationError,
    read_metadata as read_vector_metadata,
    read_vector,
)

__all__ = [
    "CRSValidationError",
    "are_equivalent",
    "crs_string",
    "normalize_crs",
    "require_same_crs",
    "RasterValidationError",
    "read_all_bands",
    "read_band",
    "read_metadata",
    "valid_statistics",
    "SatelliteDataError",
    "inspect_satellite_layer",
    "validate_satellite_stack",
    "TerrainError",
    "calculate_slope",
    "terrain_summary",
    "VectorValidationError",
    "read_vector_metadata",
    "read_vector",
]
