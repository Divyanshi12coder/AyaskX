"""
core/fault/models.py
--------------------
Immutable fault domain models for AyaskX self-healing foundation.

Phase: DETECT → LOCALIZE → RECOVERY DECISION

These dataclasses are frozen (immutable), serialization-friendly, and
carry no I/O or side-effects. They are the lingua franca shared by
FaultDetector, FaultLocalizer, and RecoveryDecisionEngine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class FaultSeverity(str, Enum):
    """
    Operational severity of a detected fault.

    LOW      - minor anomaly; pipeline can likely retry safely
    MEDIUM   - degraded execution; investigation recommended
    HIGH     - pipeline halted; recovery action required
    CRITICAL - data integrity or resource exhaustion; immediate response
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FaultType(str, Enum):
    """
    Deterministic classification of the fault origin.

    VALIDATION_ERROR   - data or output failed a validation contract
    SCHEMA_MISMATCH    - column or key missing from expected schema
    MISSING_ARTIFACT   - required file/artifact not found on disk/store
    CORRUPTED_ARTIFACT - artifact found but integrity check failed
    DEPENDENCY_FAILURE - upstream dependency failed before this node
    EXECUTION_ERROR    - generic unhandled runtime error in node logic
    TIMEOUT            - node exceeded allowed execution time
    RESOURCE_ERROR     - memory/resource exhaustion
    UNKNOWN            - error could not be classified deterministically
    """

    VALIDATION_ERROR = "validation_error"
    SCHEMA_MISMATCH = "schema_mismatch"
    MISSING_ARTIFACT = "missing_artifact"
    CORRUPTED_ARTIFACT = "corrupted_artifact"
    DEPENDENCY_FAILURE = "dependency_failure"
    EXECUTION_ERROR = "execution_error"
    TIMEOUT = "timeout"
    RESOURCE_ERROR = "resource_error"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# FaultReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FaultReport:
    """
    Result of FaultDetector.detect().

    Immutable record of what was observed at fault detection time.
    No inference beyond direct evidence from NodeExecution data.

    Fields
    ------
    execution_id   : pipeline execution that was analysed
    detected       : False when pipeline succeeded; True when a fault exists
    observed_node  : node_id of the first failed node, or None on success
    fault_type     : deterministic FaultType classification
    severity       : deterministic FaultSeverity rating
    message        : human-readable summary (for logs/audit)
    evidence       : dict of raw evidence gathered from execution data
    timestamp      : UTC time the report was created
    """

    execution_id: str
    detected: bool

    observed_node: str | None

    fault_type: FaultType
    severity: FaultSeverity

    message: str

    evidence: dict[str, Any] = field(default_factory=dict)

    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return {
            "execution_id": self.execution_id,
            "detected": self.detected,
            "observed_node": self.observed_node,
            "fault_type": self.fault_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "evidence": dict(self.evidence),
            "timestamp": self.timestamp.isoformat(),
        }


# ---------------------------------------------------------------------------
# FaultLocalization
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FaultLocalization:
    """
    Result of FaultLocalizer.localize().

    Distinguishes the OBSERVED failure node from the PROBABLE ROOT CAUSE
    node. Confidence is conservative — it reflects how much direct
    evidence supports the localization, not a vague ML score.

    Fields
    ------
    execution_id       : pipeline execution that was analysed
    observed_node      : node_id where the exception was caught
    probable_root_node : node_id most likely responsible for the failure
    confidence         : float in [0.0, 1.0]; capped at 0.95 for normal evidence
    reasoning          : human-readable explanation of the localization logic
    evidence           : list of evidence strings gathered from execution data
    """

    execution_id: str

    observed_node: str | None
    probable_root_node: str | None

    confidence: float

    reasoning: str

    evidence: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return {
            "execution_id": self.execution_id,
            "observed_node": self.observed_node,
            "probable_root_node": self.probable_root_node,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "evidence": list(self.evidence),
        }
