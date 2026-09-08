"""
CRS validation and spatial compatibility helpers.
"""

from __future__ import annotations

from typing import Any

from pyproj import CRS


class CRSValidationError(ValueError):
    """Raised when a CRS is missing or invalid."""


def normalize_crs(value: Any) -> CRS:
    if value is None:
        raise CRSValidationError("A coordinate reference system is required.")

    try:
        return CRS.from_user_input(value)
    except Exception as exc:
        raise CRSValidationError(f"Invalid CRS: {value}") from exc


def crs_string(value: Any) -> str:
    return normalize_crs(value).to_string()


def are_equivalent(crs_a: Any, crs_b: Any) -> bool:
    return normalize_crs(crs_a) == normalize_crs(crs_b)


def require_same_crs(*crs_values: Any) -> CRS:
    if not crs_values:
        raise CRSValidationError("At least one CRS is required.")

    normalized = [normalize_crs(value) for value in crs_values]

    if any(crs != normalized[0] for crs in normalized[1:]):
        raise CRSValidationError("Input layers use incompatible coordinate systems.")

    return normalized[0]
