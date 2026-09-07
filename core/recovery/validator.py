"""
core/recovery/validator.py
--------------------------
Recovery validation gate for AyaskX checkpoint-aware recovery.

RecoveryValidator checks that a recovery outcome is trustworthy before
the system accepts it. It operates AFTER the RecoveryExecutor runs a
node or restores a checkpoint.

Design principles:
- No ML performance thresholds (those belong to model evaluation).
- Deterministic structural checks only.
- Returns immutable ValidationResult — never raises on check failure.
- Reuses existing checkpoint and node execution data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.recovery.models import ValidationCheck, ValidationResult

if TYPE_CHECKING:
    from core.pipeline.checkpoints.manager import Checkpoint, CheckpointManager
    from core.pipeline.executor import NodeExecution
    from core.pipeline.status import NodeStatus


class RecoveryValidator:
    """
    Validates recovery outcomes before AyaskX accepts them.

    Checks performed (all deterministic, all structural):
    - node execution status
    - output existence
    - output schema consistency (if schema is available)
    - checkpoint integrity (data_hash present, validation_status == "passed")
    - artifact path presence (for file-backed checkpoints)
    - absence of unresolved failure

    Usage
    -----
    validator = RecoveryValidator()
    result = validator.validate_node_execution(node_exec)
    result = validator.validate_checkpoint(checkpoint, manager)
    result = validator.validate_full(node_exec, checkpoint, manager)
    """

    # -----------------------------------------------------------------------
    # Validate a NodeExecution produced during recovery
    # -----------------------------------------------------------------------

    def validate_node_execution(
        self,
        node_exec: "NodeExecution",
        *,
        expected_columns: list[str] | None = None,
    ) -> ValidationResult:
        """
        Validate a single NodeExecution outcome from a recovery rerun.

        Checks:
          1. status == SUCCESS (not FAILED/RUNNING/…)
          2. no unresolved error_type on a successful node
          3. output_metadata is populated (non-empty dict)
          4. schema consistency — if expected_columns provided, verify columns
        """

        checks: list[ValidationCheck] = []

        # Check 1: status
        from core.pipeline.status import NodeStatus

        status_ok = node_exec.status == NodeStatus.SUCCESS
        checks.append(
            ValidationCheck(
                name="node_status_success",
                passed=status_ok,
                message=(
                    f"Node '{node_exec.node_id}' status is "
                    f"'{node_exec.status.value}' "
                    f"({'OK' if status_ok else 'FAIL — expected SUCCESS'})"
                ),
            )
        )

        # Check 2: no error on success
        no_error = (
            node_exec.error_type is None
            and node_exec.error_message is None
        ) or node_exec.status != NodeStatus.SUCCESS
        checks.append(
            ValidationCheck(
                name="no_unresolved_error",
                passed=no_error,
                message=(
                    "No unresolved error_type on node execution."
                    if no_error
                    else (
                        f"Node '{node_exec.node_id}' has status SUCCESS but "
                        f"error_type='{node_exec.error_type}' is set."
                    )
                ),
            )
        )

        # Check 3: output metadata present
        has_output = bool(node_exec.output_metadata)
        checks.append(
            ValidationCheck(
                name="output_metadata_present",
                passed=has_output,
                message=(
                    "output_metadata is populated."
                    if has_output
                    else f"Node '{node_exec.node_id}' has empty output_metadata."
                ),
            )
        )

        # Check 4: schema columns (optional)
        if expected_columns is not None:
            actual_columns = node_exec.output_metadata.get("columns", None)
            if actual_columns is None:
                schema_ok = False
                schema_msg = "No 'columns' key in output_metadata for schema check."
            else:
                missing = [c for c in expected_columns if c not in actual_columns]
                schema_ok = len(missing) == 0
                schema_msg = (
                    "Schema columns match."
                    if schema_ok
                    else f"Missing columns: {missing}"
                )
            checks.append(
                ValidationCheck(
                    name="schema_columns_match",
                    passed=schema_ok,
                    message=schema_msg,
                )
            )

        return self._build_result(checks)

    # -----------------------------------------------------------------------
    # Validate a Checkpoint
    # -----------------------------------------------------------------------

    def validate_checkpoint(
        self,
        checkpoint: "Checkpoint",
        manager: "CheckpointManager | None" = None,
    ) -> ValidationResult:
        """
        Validate a checkpoint's integrity before using it for recovery.

        Checks:
          1. checkpoint_id is non-empty
          2. validation_status == "passed"
          3. data_hash is non-empty
          4. artifact_path exists on disk (if manager provides restore)
        """

        checks: list[ValidationCheck] = []

        # Check 1: checkpoint_id
        has_id = bool(getattr(checkpoint, "checkpoint_id", None))
        checks.append(
            ValidationCheck(
                name="checkpoint_id_present",
                passed=has_id,
                message=(
                    f"checkpoint_id='{checkpoint.checkpoint_id}'"
                    if has_id
                    else "checkpoint_id is missing or empty."
                ),
            )
        )

        # Check 2: validation_status
        vstatus = getattr(checkpoint, "validation_status", "")
        status_ok = vstatus == "passed"
        checks.append(
            ValidationCheck(
                name="validation_status_passed",
                passed=status_ok,
                message=(
                    "validation_status == 'passed'."
                    if status_ok
                    else f"validation_status is '{vstatus}', expected 'passed'."
                ),
            )
        )

        # Check 3: data_hash
        has_hash = bool(getattr(checkpoint, "data_hash", None))
        checks.append(
            ValidationCheck(
                name="data_hash_present",
                passed=has_hash,
                message=(
                    "data_hash is present."
                    if has_hash
                    else "data_hash is missing — checkpoint integrity unknown."
                ),
            )
        )

        # Check 4: artifact path accessible (if checkpoint has one)
        artifact_path = getattr(checkpoint, "artifact_path", None)
        if artifact_path is not None:
            from pathlib import Path

            path_exists = Path(artifact_path).exists()
            checks.append(
                ValidationCheck(
                    name="artifact_path_exists",
                    passed=path_exists,
                    message=(
                        f"Artifact at '{artifact_path}' exists."
                        if path_exists
                        else f"Artifact path '{artifact_path}' does not exist on disk."
                    ),
                )
            )
        else:
            # No artifact_path — in-memory checkpoint; treat as OK
            checks.append(
                ValidationCheck(
                    name="artifact_path_exists",
                    passed=True,
                    message="No artifact_path — in-memory checkpoint (OK).",
                )
            )

        return self._build_result(checks)

    # -----------------------------------------------------------------------
    # Full validation: node execution + checkpoint
    # -----------------------------------------------------------------------

    def validate_full(
        self,
        node_exec: "NodeExecution",
        checkpoint: "Checkpoint | None" = None,
        manager: "CheckpointManager | None" = None,
        *,
        expected_columns: list[str] | None = None,
    ) -> ValidationResult:
        """
        Combined validation of both node execution and checkpoint.

        Runs validate_node_execution + validate_checkpoint and merges results.
        """

        node_result = self.validate_node_execution(
            node_exec,
            expected_columns=expected_columns,
        )

        if checkpoint is not None:
            ckpt_result = self.validate_checkpoint(checkpoint, manager)
            all_checks = node_result.checks + ckpt_result.checks
        else:
            all_checks = node_result.checks

        return self._build_result(list(all_checks))

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    # -----------------------------------------------------------------------
    # Validate artifact integrity (Phase J)
    # -----------------------------------------------------------------------

    def validate_artifact_integrity(
        self,
        artifact_path: "str | Path | None",
        integrity_result: "IntegrityResult | None" = None,
    ) -> ValidationResult:
        """
        Validate that an artifact is present, readable, and integrity-verified.

        Checks:
          1. artifact_path is provided and not None
          2. artifact file exists on disk
          3. integrity_result is provided (was checked before calling this)
          4. integrity check passed (status == PASSED or NO_MANIFEST for legacy)

        Parameters
        ----------
        artifact_path     : path to the artifact on disk
        integrity_result  : result from ArtifactIntegrityChecker.verify()
                            (None → treated as "not checked")
        """
        from pathlib import Path

        checks: list[ValidationCheck] = []

        # Check 1: path provided
        has_path = artifact_path is not None
        checks.append(ValidationCheck(
            name="artifact_path_provided",
            passed=has_path,
            message=(
                f"artifact_path='{artifact_path}'"
                if has_path
                else "artifact_path is None — cannot validate artifact."
            ),
        ))

        # Check 2: file exists
        if has_path:
            path_exists = Path(artifact_path).exists()
            checks.append(ValidationCheck(
                name="artifact_exists_on_disk",
                passed=path_exists,
                message=(
                    f"Artifact exists at '{artifact_path}'."
                    if path_exists
                    else f"Artifact not found on disk: '{artifact_path}'."
                ),
            ))
        else:
            checks.append(ValidationCheck(
                name="artifact_exists_on_disk",
                passed=False,
                message="Cannot check existence — path not provided.",
            ))

        # Check 3: integrity result provided
        has_result = integrity_result is not None
        checks.append(ValidationCheck(
            name="integrity_check_was_performed",
            passed=has_result,
            message=(
                "Integrity check result is available."
                if has_result
                else "No integrity check was performed — treating as unverified."
            ),
        ))

        # Check 4: integrity passed (PASSED) or legacy (NO_MANIFEST is acceptable)
        if has_result:
            from core.integrity.models import IntegrityStatus
            passed_statuses = {IntegrityStatus.PASSED, IntegrityStatus.NO_MANIFEST}
            integrity_ok = integrity_result.status in passed_statuses
            checks.append(ValidationCheck(
                name="integrity_check_passed",
                passed=integrity_ok,
                message=(
                    f"Integrity status: {integrity_result.status.value} (acceptable)."
                    if integrity_ok
                    else (
                        f"Integrity check FAILED: {integrity_result.reason}"
                    )
                ),
            ))
        else:
            checks.append(ValidationCheck(
                name="integrity_check_passed",
                passed=False,
                message="No integrity result to evaluate.",
            ))

        return self._build_result(checks)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _build_result(
        checks: list[ValidationCheck],
    ) -> ValidationResult:
        failures = tuple(c.name for c in checks if not c.passed)
        passed = len(failures) == 0
        message = (
            "All validation checks passed."
            if passed
            else f"Validation failed: {', '.join(failures)}"
        )
        return ValidationResult(
            passed=passed,
            checks=tuple(checks),
            failures=failures,
            message=message,
        )
