"""
core/recovery/decision.py
-------------------------
Deterministic recovery decision engine for AyaskX self-healing foundation.

CRITICAL CONSTRAINT:
    This engine is a PURE POLICY ENGINE.
    It produces a RecoveryDecision describing WHAT to do.
    It NEVER executes, retries, rolls back, quarantines, or deploys anything.
    It has NO side effects.
    It performs NO I/O.

Phase: DETECT → LOCALIZE → RECOVERY DECISION
Next:  CHECKPOINT-AWARE RECOVERY EXECUTION (future phase)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from core.fault.models import FaultSeverity, FaultType

if TYPE_CHECKING:
    from core.fault.models import FaultLocalization, FaultReport
    from core.pipeline.executor import PipelineExecution


# ---------------------------------------------------------------------------
# RecoveryActionType
# ---------------------------------------------------------------------------


class RecoveryActionType(str, Enum):
    """
    The prescribed recovery action for a detected fault.

    RETRY           - re-execute the pipeline from the beginning (safe for
                      LOW severity or transient failures with no state change)
    RERUN_FROM_NODE - re-execute from a specific node (requires a valid
                      checkpoint at the preceding node)
    ROLLBACK        - restore to last-known-good checkpoint
    QUARANTINE      - isolate the affected component; do not retry until
                      manual inspection clears it
    MANUAL_REVIEW   - human review required before any automated action
    ABORT           - no safe automated path; stop the pipeline entirely
    """

    RETRY = "retry"
    RERUN_FROM_NODE = "rerun_from_node"
    ROLLBACK = "rollback"
    QUARANTINE = "quarantine"
    MANUAL_REVIEW = "manual_review"
    ABORT = "abort"


# ---------------------------------------------------------------------------
# RecoveryDecision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecoveryDecision:
    """
    Immutable record of the recovery decision produced by
    RecoveryDecisionEngine.decide().

    Fields
    ------
    execution_id      : pipeline execution this decision applies to
    action            : the prescribed RecoveryActionType
    requires_approval : True when human confirmation is required before acting
    reason            : human-readable rationale for the decision
    target_node       : node_id to restart from (for RERUN_FROM_NODE)
    checkpoint_id     : checkpoint to restore (for ROLLBACK)
    evidence          : supporting evidence dict (for auditing)
    confidence        : confidence in the decision [0.0, 1.0]
    """

    execution_id: str
    action: RecoveryActionType
    requires_approval: bool
    reason: str

    target_node: str | None = None
    checkpoint_id: str | None = None

    evidence: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""
        return {
            "execution_id": self.execution_id,
            "action": self.action.value,
            "requires_approval": self.requires_approval,
            "reason": self.reason,
            "target_node": self.target_node,
            "checkpoint_id": self.checkpoint_id,
            "evidence": dict(self.evidence),
            "confidence": self.confidence,
        }


# ---------------------------------------------------------------------------
# RecoveryDecisionEngine
# ---------------------------------------------------------------------------


class RecoveryDecisionEngine:
    """
    Produces a deterministic RecoveryDecision given fault analysis outputs.

    Decision rules are evaluated in strict priority order.

    This class has NO state and NO side effects.
    Instantiate once and reuse freely.
    """

    def decide(
        self,
        execution: "PipelineExecution",
        fault: "FaultReport",
        localization: "FaultLocalization",
        last_known_good_checkpoint: Any = None,
    ) -> RecoveryDecision:
        """
        Evaluate fault information and return a RecoveryDecision.

        Parameters
        ----------
        execution                  : the completed PipelineExecution
        fault                      : FaultReport from FaultDetector
        localization               : FaultLocalization from FaultLocalizer
        last_known_good_checkpoint : Checkpoint object or None
        """

        eid = execution.execution_id
        has_checkpoint = last_known_good_checkpoint is not None

        checkpoint_id: str | None = (
            getattr(last_known_good_checkpoint, "checkpoint_id", None)
            if has_checkpoint
            else None
        )

        # ------------------------------------------------------------------
        # RULE 0 — No fault detected: safe to retry
        # ------------------------------------------------------------------

        if not fault.detected:
            return RecoveryDecision(
                execution_id=eid,
                action=RecoveryActionType.RETRY,
                requires_approval=False,
                reason=(
                    "No fault was detected. Pipeline completed successfully. "
                    "A simple retry is safe."
                ),
                confidence=1.0,
                evidence={"fault_detected": False},
            )

        # ------------------------------------------------------------------
        # RULE 1 — LOW severity: retry
        # ------------------------------------------------------------------

        if fault.severity == FaultSeverity.LOW:
            return RecoveryDecision(
                execution_id=eid,
                action=RecoveryActionType.RETRY,
                requires_approval=False,
                reason=(
                    f"Fault severity is LOW. A retry is the safest and "
                    f"least disruptive action. "
                    f"Fault type: {fault.fault_type.value}."
                ),
                confidence=0.90,
                evidence={
                    "severity": fault.severity.value,
                    "fault_type": fault.fault_type.value,
                },
            )

        # ------------------------------------------------------------------
        # RULE 2 — CORRUPTED_ARTIFACT with security/integrity evidence
        #          → QUARANTINE (highest priority among artifact faults)
        # ------------------------------------------------------------------

        if fault.fault_type == FaultType.CORRUPTED_ARTIFACT:
            # Check if the error message contains security/integrity hints
            evidence_msg = fault.evidence.get("error_message", "")
            error_type = fault.evidence.get("error_type", "")
            security_keywords = (
                "integrity",
                "tamper",
                "corrupt",
                "security",
                "breach",
                "unauthori",
            )
            has_security_hint = (
                error_type in ("SecurityError", "IntegrityError")
                or any(kw in evidence_msg.lower() for kw in security_keywords)
            )

            if has_security_hint:
                return RecoveryDecision(
                    execution_id=eid,
                    action=RecoveryActionType.QUARANTINE,
                    requires_approval=True,
                    reason=(
                        f"CORRUPTED_ARTIFACT fault with explicit "
                        f"security/integrity evidence. "
                        f"Component '{fault.observed_node}' must be "
                        f"quarantined pending investigation. "
                        f"Do NOT retry automatically."
                    ),
                    target_node=fault.observed_node,
                    confidence=0.95,
                    evidence={
                        "fault_type": fault.fault_type.value,
                        "severity": fault.severity.value,
                        "error_type": error_type,
                        "error_message": evidence_msg,
                    },
                )

            # CORRUPTED_ARTIFACT without security hint — try rollback
            if has_checkpoint:
                return RecoveryDecision(
                    execution_id=eid,
                    action=RecoveryActionType.ROLLBACK,
                    requires_approval=True,
                    reason=(
                        f"CORRUPTED_ARTIFACT at node '{fault.observed_node}' "
                        f"without explicit security evidence. "
                        f"Rolling back to last-known-good checkpoint "
                        f"'{checkpoint_id}'."
                    ),
                    target_node=localization.probable_root_node,
                    checkpoint_id=checkpoint_id,
                    confidence=0.80,
                    evidence={
                        "fault_type": fault.fault_type.value,
                        "checkpoint_id": checkpoint_id,
                    },
                )

            # No checkpoint available — abort
            return RecoveryDecision(
                execution_id=eid,
                action=RecoveryActionType.ABORT,
                requires_approval=True,
                reason=(
                    f"CORRUPTED_ARTIFACT at node '{fault.observed_node}' "
                    f"with no valid checkpoint available for rollback. "
                    f"Automated recovery is not safe."
                ),
                target_node=fault.observed_node,
                confidence=0.90,
                evidence={"fault_type": fault.fault_type.value},
            )

        # ------------------------------------------------------------------
        # RULE 3 — VALIDATION_ERROR or SCHEMA_MISMATCH with identified node
        #          → RERUN_FROM_NODE
        # ------------------------------------------------------------------

        if fault.fault_type in (
            FaultType.VALIDATION_ERROR,
            FaultType.SCHEMA_MISMATCH,
        ):
            root_node = localization.probable_root_node or fault.observed_node
            if root_node is not None:
                return RecoveryDecision(
                    execution_id=eid,
                    action=RecoveryActionType.RERUN_FROM_NODE,
                    requires_approval=False,
                    reason=(
                        f"Fault type {fault.fault_type.value} with "
                        f"localized root node '{root_node}'. "
                        f"Re-running from this node is the targeted recovery."
                    ),
                    target_node=root_node,
                    checkpoint_id=checkpoint_id,
                    confidence=localization.confidence,
                    evidence={
                        "fault_type": fault.fault_type.value,
                        "root_node": root_node,
                        "localization_confidence": localization.confidence,
                    },
                )

        # ------------------------------------------------------------------
        # RULE 4 — MISSING_ARTIFACT with valid checkpoint → ROLLBACK
        # ------------------------------------------------------------------

        if fault.fault_type == FaultType.MISSING_ARTIFACT:
            if has_checkpoint:
                return RecoveryDecision(
                    execution_id=eid,
                    action=RecoveryActionType.ROLLBACK,
                    requires_approval=True,
                    reason=(
                        f"MISSING_ARTIFACT at node '{fault.observed_node}'. "
                        f"A valid last-known-good checkpoint "
                        f"'{checkpoint_id}' exists. "
                        f"Rolling back to restore the missing artifact."
                    ),
                    target_node=localization.probable_root_node,
                    checkpoint_id=checkpoint_id,
                    confidence=0.85,
                    evidence={
                        "fault_type": fault.fault_type.value,
                        "checkpoint_id": checkpoint_id,
                    },
                )
            # No checkpoint — abort
            return RecoveryDecision(
                execution_id=eid,
                action=RecoveryActionType.ABORT,
                requires_approval=True,
                reason=(
                    f"MISSING_ARTIFACT at node '{fault.observed_node}' "
                    f"with no valid checkpoint for rollback. "
                    f"Cannot recover automatically."
                ),
                target_node=fault.observed_node,
                confidence=0.90,
                evidence={"fault_type": fault.fault_type.value},
            )

        # ------------------------------------------------------------------
        # RULE 5 — DEPENDENCY_FAILURE → RERUN_FROM_NODE if localized,
        #          else ROLLBACK if checkpoint, else MANUAL_REVIEW
        # ------------------------------------------------------------------

        if fault.fault_type == FaultType.DEPENDENCY_FAILURE:
            root_node = localization.probable_root_node
            if root_node and root_node != fault.observed_node:
                return RecoveryDecision(
                    execution_id=eid,
                    action=RecoveryActionType.RERUN_FROM_NODE,
                    requires_approval=False,
                    reason=(
                        f"DEPENDENCY_FAILURE observed at '{fault.observed_node}' "
                        f"but root cause localized to '{root_node}'. "
                        f"Re-run from root cause node."
                    ),
                    target_node=root_node,
                    checkpoint_id=checkpoint_id,
                    confidence=localization.confidence,
                    evidence={
                        "fault_type": fault.fault_type.value,
                        "root_node": root_node,
                    },
                )
            if has_checkpoint:
                return RecoveryDecision(
                    execution_id=eid,
                    action=RecoveryActionType.ROLLBACK,
                    requires_approval=True,
                    reason=(
                        f"DEPENDENCY_FAILURE at '{fault.observed_node}' "
                        f"with no better upstream localization. "
                        f"Rolling back to checkpoint '{checkpoint_id}'."
                    ),
                    checkpoint_id=checkpoint_id,
                    confidence=0.70,
                    evidence={"fault_type": fault.fault_type.value},
                )
            return RecoveryDecision(
                execution_id=eid,
                action=RecoveryActionType.MANUAL_REVIEW,
                requires_approval=True,
                reason=(
                    f"DEPENDENCY_FAILURE at '{fault.observed_node}' "
                    f"with no checkpoint and no upstream localization. "
                    f"Manual review required."
                ),
                confidence=0.60,
                evidence={"fault_type": fault.fault_type.value},
            )

        # ------------------------------------------------------------------
        # RULE 6 — CRITICAL severity + UNKNOWN/EXECUTION_ERROR
        #          → MANUAL_REVIEW
        # ------------------------------------------------------------------

        if fault.severity == FaultSeverity.CRITICAL:
            return RecoveryDecision(
                execution_id=eid,
                action=RecoveryActionType.MANUAL_REVIEW,
                requires_approval=True,
                reason=(
                    f"CRITICAL severity fault ({fault.fault_type.value}) "
                    f"at node '{fault.observed_node}'. "
                    f"Automated recovery is not safe for CRITICAL faults "
                    f"without a well-understood recovery path."
                ),
                target_node=fault.observed_node,
                confidence=0.90,
                evidence={
                    "severity": fault.severity.value,
                    "fault_type": fault.fault_type.value,
                },
            )

        # ------------------------------------------------------------------
        # RULE 7 — EXECUTION_ERROR / UNKNOWN with checkpoint → ROLLBACK
        # ------------------------------------------------------------------

        if fault.fault_type in (
            FaultType.EXECUTION_ERROR,
            FaultType.UNKNOWN,
        ):
            if has_checkpoint:
                return RecoveryDecision(
                    execution_id=eid,
                    action=RecoveryActionType.ROLLBACK,
                    requires_approval=True,
                    reason=(
                        f"Fault type {fault.fault_type.value} at node "
                        f"'{fault.observed_node}'. "
                        f"Rolling back to last-known-good checkpoint "
                        f"'{checkpoint_id}' as the safest option."
                    ),
                    checkpoint_id=checkpoint_id,
                    target_node=localization.probable_root_node,
                    confidence=0.70,
                    evidence={
                        "fault_type": fault.fault_type.value,
                        "checkpoint_id": checkpoint_id,
                    },
                )
            return RecoveryDecision(
                execution_id=eid,
                action=RecoveryActionType.ABORT,
                requires_approval=True,
                reason=(
                    f"Fault type {fault.fault_type.value} at node "
                    f"'{fault.observed_node}' with no valid checkpoint. "
                    f"No safe automated recovery path available."
                ),
                target_node=fault.observed_node,
                confidence=0.80,
                evidence={"fault_type": fault.fault_type.value},
            )

        # ------------------------------------------------------------------
        # RULE 8 — TIMEOUT / RESOURCE_ERROR
        # ------------------------------------------------------------------

        if fault.fault_type in (
            FaultType.TIMEOUT,
            FaultType.RESOURCE_ERROR,
        ):
            if has_checkpoint:
                return RecoveryDecision(
                    execution_id=eid,
                    action=RecoveryActionType.ROLLBACK,
                    requires_approval=True,
                    reason=(
                        f"Fault type {fault.fault_type.value} at node "
                        f"'{fault.observed_node}'. "
                        f"Rolling back to checkpoint '{checkpoint_id}' "
                        f"before retrying with adjusted resources."
                    ),
                    checkpoint_id=checkpoint_id,
                    confidence=0.75,
                    evidence={
                        "fault_type": fault.fault_type.value,
                        "checkpoint_id": checkpoint_id,
                    },
                )
            return RecoveryDecision(
                execution_id=eid,
                action=RecoveryActionType.MANUAL_REVIEW,
                requires_approval=True,
                reason=(
                    f"Fault type {fault.fault_type.value} at node "
                    f"'{fault.observed_node}' with no checkpoint. "
                    f"Manual review required to assess resource constraints."
                ),
                target_node=fault.observed_node,
                confidence=0.65,
                evidence={"fault_type": fault.fault_type.value},
            )

        # ------------------------------------------------------------------
        # FALLBACK — any other unhandled case → ABORT
        # ------------------------------------------------------------------

        return RecoveryDecision(
            execution_id=eid,
            action=RecoveryActionType.ABORT,
            requires_approval=True,
            reason=(
                f"Unhandled fault type '{fault.fault_type.value}' "
                f"(severity={fault.severity.value}) at node "
                f"'{fault.observed_node}'. "
                f"Aborting: no safe automated recovery rule matched."
            ),
            target_node=fault.observed_node,
            confidence=0.50,
            evidence={
                "fault_type": fault.fault_type.value,
                "severity": fault.severity.value,
                "reason": "no_matching_recovery_rule",
            },
        )
