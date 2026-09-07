"""
core/fault/__init__.py
----------------------
Public API for the AyaskX fault detection and localization subsystem.

Phase: DETECT → LOCALIZE → RECOVERY DECISION
"""

from core.fault.models import (
    FaultLocalization,
    FaultReport,
    FaultSeverity,
    FaultType,
)
from core.fault.detector import FaultDetector
from core.fault.localizer import FaultLocalizer


__all__ = [
    # Enums
    "FaultSeverity",
    "FaultType",
    # Dataclasses
    "FaultReport",
    "FaultLocalization",
    # Engines
    "FaultDetector",
    "FaultLocalizer",
]
