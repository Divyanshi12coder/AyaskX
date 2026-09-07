"""
core/fault/detector.py
----------------------
Deterministic fault detection for AyaskX pipeline executions.

Rules are documented inline with their classification logic.
No ML, no LLM, no I/O. Pure function of PipelineExecution data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.fault.models import (
    FaultReport,
    FaultSeverity,
    FaultType,
)
from core.pipeline.status import PipelineStatus

if TYPE_CHECKING:
    from core.pipeline.executor import PipelineExecution


class FaultDetector:
    """
    Detects and classifies pipeline faults from a PipelineExecution record.

    Usage
    -----
    detector = FaultDetector()
    report = detector.detect(execution)

    The returned FaultReport is immutable and side-effect free.
    """

    def detect(
        self,
        execution: "PipelineExecution",
    ) -> FaultReport:
        """
        Analyse a completed PipelineExecution and return a FaultReport.

        If the pipeline succeeded, returns a report with detected=False.
        If the pipeline failed, classifies the fault deterministically
        from error_type and error_message on the failed NodeExecution.
        """

        # ------------------------------------------------------------------
        # SUCCESS — no fault
        # ------------------------------------------------------------------

        if execution.status == PipelineStatus.SUCCESS:
            return FaultReport(
                execution_id=execution.execution_id,
                detected=False,
                observed_node=None,
                fault_type=FaultType.UNKNOWN,
                severity=FaultSeverity.LOW,
                message="Pipeline completed successfully. No fault detected.",
                evidence={},
            )

        # ------------------------------------------------------------------
        # FAILURE — locate the first failed node
        # ------------------------------------------------------------------

        failed = execution.failed_node

        if failed is None:
            # Pipeline status is FAILED but no node recorded FAILED status.
            # This is an unusual state — report conservatively.
            return FaultReport(
                execution_id=execution.execution_id,
                detected=True,
                observed_node=None,
                fault_type=FaultType.UNKNOWN,
                severity=FaultSeverity.HIGH,
                message=(
                    "Pipeline status is FAILED but no failed node was "
                    "recorded. This is an unexpected execution state."
                ),
                evidence={
                    "pipeline_status": execution.status.value,
                    "node_count": len(execution.nodes),
                },
            )

        # ------------------------------------------------------------------
        # Collect raw evidence from the failed node
        # ------------------------------------------------------------------

        error_type: str = failed.error_type or ""
        error_message: str = failed.error_message or ""
        msg_lower = error_message.lower()

        evidence: dict[str, Any] = {
            "node_id": failed.node_id,
            "error_type": error_type,
            "error_message": error_message,
            "node_status": failed.status.value,
        }

        if failed.input_metadata:
            evidence["input_metadata"] = dict(failed.input_metadata)

        # ------------------------------------------------------------------
        # Deterministic classification
        # ------------------------------------------------------------------

        fault_type, severity, message = self._classify(
            error_type=error_type,
            error_message=error_message,
            msg_lower=msg_lower,
            node_id=failed.node_id,
        )

        return FaultReport(
            execution_id=execution.execution_id,
            detected=True,
            observed_node=failed.node_id,
            fault_type=fault_type,
            severity=severity,
            message=message,
            evidence=evidence,
        )

    # -----------------------------------------------------------------------
    # Classification rules (static, documented)
    # -----------------------------------------------------------------------

    @staticmethod
    def _classify(
        *,
        error_type: str,
        error_message: str,
        msg_lower: str,
        node_id: str,
    ) -> tuple[FaultType, FaultSeverity, str]:
        """
        Map error_type + error_message → (FaultType, FaultSeverity, message).

        Rules are evaluated in priority order.  The first matching rule wins.
        All matching is deterministic string comparison — no heuristics.
        """

        # ------------------------------------------------------------------
        # KeyError — schema mismatch
        # ------------------------------------------------------------------
        # "column" in message → specifically a dataframe schema violation
        # generic KeyError    → key missing from dict/mapping

        if error_type == "KeyError":
            if "column" in msg_lower:
                return (
                    FaultType.SCHEMA_MISMATCH,
                    FaultSeverity.HIGH,
                    (
                        f"Node '{node_id}' raised KeyError referencing a "
                        f"missing column: {error_message}"
                    ),
                )
            return (
                FaultType.SCHEMA_MISMATCH,
                FaultSeverity.MEDIUM,
                (
                    f"Node '{node_id}' raised KeyError — "
                    f"expected key missing: {error_message}"
                ),
            )

        # ------------------------------------------------------------------
        # FileNotFoundError — missing artifact
        # ------------------------------------------------------------------

        if error_type == "FileNotFoundError":
            return (
                FaultType.MISSING_ARTIFACT,
                FaultSeverity.HIGH,
                (
                    f"Node '{node_id}' could not locate a required artifact "
                    f"or file: {error_message}"
                ),
            )

        # ------------------------------------------------------------------
        # ValueError — validation-related
        # ------------------------------------------------------------------
        # "output validation" is the more specific and higher severity case
        # "validation" is the broader case

        if error_type == "ValueError":
            if "output validation" in msg_lower:
                return (
                    FaultType.VALIDATION_ERROR,
                    FaultSeverity.HIGH,
                    (
                        f"Node '{node_id}' failed output validation: "
                        f"{error_message}"
                    ),
                )
            if "validation" in msg_lower:
                return (
                    FaultType.VALIDATION_ERROR,
                    FaultSeverity.MEDIUM,
                    (
                        f"Node '{node_id}' encountered a validation error: "
                        f"{error_message}"
                    ),
                )
            # Generic ValueError — treat as execution error
            return (
                FaultType.EXECUTION_ERROR,
                FaultSeverity.MEDIUM,
                (
                    f"Node '{node_id}' raised ValueError: {error_message}"
                ),
            )

        # ------------------------------------------------------------------
        # TimeoutError — execution exceeded allowed time
        # ------------------------------------------------------------------

        if error_type == "TimeoutError":
            return (
                FaultType.TIMEOUT,
                FaultSeverity.HIGH,
                (
                    f"Node '{node_id}' timed out during execution: "
                    f"{error_message}"
                ),
            )

        # ------------------------------------------------------------------
        # MemoryError — resource exhaustion
        # ------------------------------------------------------------------

        if error_type == "MemoryError":
            return (
                FaultType.RESOURCE_ERROR,
                FaultSeverity.CRITICAL,
                (
                    f"Node '{node_id}' exhausted available memory: "
                    f"{error_message}"
                ),
            )

        # ------------------------------------------------------------------
        # PermissionError
        # ------------------------------------------------------------------
        # We do NOT blindly classify every PermissionError as
        # CORRUPTED_ARTIFACT.  It is most likely a missing_artifact /
        # environment issue.  Only an explicit security/integrity message
        # would warrant CORRUPTED_ARTIFACT.

        if error_type == "PermissionError":
            if any(
                kw in msg_lower
                for kw in ("integrity", "tamper", "corrupt", "security")
            ):
                return (
                    FaultType.CORRUPTED_ARTIFACT,
                    FaultSeverity.CRITICAL,
                    (
                        f"Node '{node_id}' PermissionError with "
                        f"integrity/security hint: {error_message}"
                    ),
                )
            return (
                FaultType.MISSING_ARTIFACT,
                FaultSeverity.HIGH,
                (
                    f"Node '{node_id}' was denied access to a required "
                    f"resource: {error_message}"
                ),
            )

        # ------------------------------------------------------------------
        # Explicit SecurityError / integrity
        # ------------------------------------------------------------------

        if error_type in ("SecurityError", "IntegrityError"):
            return (
                FaultType.CORRUPTED_ARTIFACT,
                FaultSeverity.CRITICAL,
                (
                    f"Node '{node_id}' raised {error_type} indicating "
                    f"potential data corruption or security event: "
                    f"{error_message}"
                ),
            )

        # ------------------------------------------------------------------
        # RuntimeError — dependency or generic execution error
        # ------------------------------------------------------------------

        if error_type == "RuntimeError":
            if "dependency" in msg_lower:
                return (
                    FaultType.DEPENDENCY_FAILURE,
                    FaultSeverity.HIGH,
                    (
                        f"Node '{node_id}' reported a dependency failure: "
                        f"{error_message}"
                    ),
                )
            return (
                FaultType.EXECUTION_ERROR,
                FaultSeverity.MEDIUM,
                (
                    f"Node '{node_id}' raised RuntimeError: {error_message}"
                ),
            )

        # ------------------------------------------------------------------
        # Anything else — unknown / generic execution error
        # ------------------------------------------------------------------

        if error_type:
            return (
                FaultType.EXECUTION_ERROR,
                FaultSeverity.MEDIUM,
                (
                    f"Node '{node_id}' raised {error_type}: {error_message}"
                ),
            )

        return (
            FaultType.UNKNOWN,
            FaultSeverity.MEDIUM,
            (
                f"Node '{node_id}' failed with an unclassified error. "
                f"Message: {error_message}"
            ),
        )
