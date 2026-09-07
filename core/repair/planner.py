"""
core/repair/planner.py
-----------------------
Deterministic Repair Planner for AyaskX self-healing foundation.

Phase H: REPAIR PLANNER

Input:  RootCauseReport
Output: RepairPlan — ordered, deterministic, auditable repair steps.

Design principles:
- NO code generation.
- NO modification of production source code.
- NO arbitrary Python execution.
- Each step declares: action_type, target, reason, required_checkpoint,
  risk_level, requires_validation.
- Ordered by risk (lowest risk first).
- Result is frozen and auditable.

Repair actions:
    RERUN_NODE               — rerun a specific node from current state
    RERUN_FROM_CHECKPOINT    — restore checkpoint then rerun from target node
    RESTORE_CHECKPOINT       — rollback to last-known-good checkpoint
    RESTORE_CONFIGURATION    — restore a previous validated configuration
    REBUILD_ARTIFACT         — rebuild a missing/corrupted intermediate artifact
    REMAP_SCHEMA             — remap schema discrepancy at target node
    USE_VALIDATED_PREPROCESSING — apply previously validated preprocessing config
    SWITCH_MODEL_CANDIDATE   — select a different already-validated model candidate
    MANUAL_REVIEW            — escalate to human (no automated action)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.analysis.root_cause import RootCauseReport


# ---------------------------------------------------------------------------
# RepairActionType
# ---------------------------------------------------------------------------


class RepairActionType:
    """String constants for deterministic repair action types."""

    RERUN_NODE = "RERUN_NODE"
    RERUN_FROM_CHECKPOINT = "RERUN_FROM_CHECKPOINT"
    RESTORE_CHECKPOINT = "RESTORE_CHECKPOINT"
    RESTORE_CONFIGURATION = "RESTORE_CONFIGURATION"
    REBUILD_ARTIFACT = "REBUILD_ARTIFACT"
    REMAP_SCHEMA = "REMAP_SCHEMA"
    USE_VALIDATED_PREPROCESSING = "USE_VALIDATED_PREPROCESSING"
    SWITCH_MODEL_CANDIDATE = "SWITCH_MODEL_CANDIDATE"
    MANUAL_REVIEW = "MANUAL_REVIEW"


# ---------------------------------------------------------------------------
# RiskLevel
# ---------------------------------------------------------------------------


class RiskLevel:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# RepairStep
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepairStep:
    """
    A single deterministic repair step.

    Fields
    ------
    step_index          : order in the plan (0-based)
    action_type         : RepairActionType constant
    target_node         : node_id to act on (may be None for pipeline-wide)
    target_artifact     : artifact name/path (optional)
    reason              : human-readable rationale
    required_checkpoint : checkpoint_id required for this step (may be None)
    risk_level          : RiskLevel constant
    requires_validation : True if a validation gate must pass before continuing
    metadata            : additional step-specific data
    """

    step_index: int
    action_type: str
    target_node: str | None
    target_artifact: str | None
    reason: str
    required_checkpoint: str | None
    risk_level: str
    requires_validation: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "action_type": self.action_type,
            "target_node": self.target_node,
            "target_artifact": self.target_artifact,
            "reason": self.reason,
            "required_checkpoint": self.required_checkpoint,
            "risk_level": self.risk_level,
            "requires_validation": self.requires_validation,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# RepairPlan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepairPlan:
    """
    Immutable, ordered, deterministic repair plan.

    Produced by RepairPlanner.plan() from a RootCauseReport.

    Fields
    ------
    execution_id        : original failed execution_id
    hypothesis_category : top hypothesis category from RootCauseReport
    steps               : ordered tuple of RepairStep (step_index ascending)
    root_node           : localized root cause node (may be None)
    requires_approval   : True if any step has risk_level >= HIGH or MANUAL_REVIEW
    rationale           : human-readable overall rationale
    planned_at          : UTC timestamp
    """

    execution_id: str
    hypothesis_category: str
    steps: tuple[RepairStep, ...]
    root_node: str | None
    requires_approval: bool
    rationale: str
    planned_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def has_automated_steps(self) -> bool:
        return any(
            s.action_type != RepairActionType.MANUAL_REVIEW
            for s in self.steps
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "hypothesis_category": self.hypothesis_category,
            "root_node": self.root_node,
            "requires_approval": self.requires_approval,
            "rationale": self.rationale,
            "step_count": self.step_count,
            "steps": [s.to_dict() for s in self.steps],
            "planned_at": self.planned_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# RepairPlanner
# ---------------------------------------------------------------------------


class RepairPlanner:
    """
    Converts a RootCauseReport into a deterministic RepairPlan.

    Rules:
    - Lowest-risk actions first.
    - Never generate arbitrary Python.
    - Never modify production source.
    - Always declare required checkpoint.
    - Always require validation after risky steps.

    Usage
    -----
    planner = RepairPlanner()
    plan = planner.plan(root_cause_report, last_known_good_checkpoint="ckpt-001")
    """

    def plan(
        self,
        report: "RootCauseReport",
        *,
        last_known_good_checkpoint: str | None = None,
        available_model_candidates: tuple[str, ...] = (),
    ) -> RepairPlan:
        """
        Produce a RepairPlan from a RootCauseReport.

        Parameters
        ----------
        report                       : RootCauseReport from RootCauseAnalyzer
        last_known_good_checkpoint   : checkpoint_id for rollback/rerun steps
        available_model_candidates   : names of already-trained candidates to
                                       switch to (for model selection failures)
        """

        top = report.top_hypothesis()
        category = top.category if top else "UNKNOWN"

        steps = self._build_steps(
            category=category,
            report=report,
            lkg_checkpoint=last_known_good_checkpoint,
            model_candidates=available_model_candidates,
        )

        requires_approval = any(
            s.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
            or s.action_type == RepairActionType.MANUAL_REVIEW
            for s in steps
        )

        rationale = self._build_rationale(category, report)

        return RepairPlan(
            execution_id=report.execution_id,
            hypothesis_category=category,
            steps=tuple(steps),
            root_node=report.root_node,
            requires_approval=requires_approval,
            rationale=rationale,
            planned_at=datetime.now(timezone.utc),
        )

    # -----------------------------------------------------------------------
    # Step builders by hypothesis category
    # -----------------------------------------------------------------------

    def _build_steps(
        self,
        category: str,
        report: "RootCauseReport",
        lkg_checkpoint: str | None,
        model_candidates: tuple[str, ...],
    ) -> list[RepairStep]:

        root = report.root_node

        if category == "SCHEMA_MISMATCH":
            return self._steps_schema_mismatch(root, lkg_checkpoint)

        elif category == "MISSING_ARTIFACT":
            return self._steps_missing_artifact(root, lkg_checkpoint)

        elif category == "CORRUPTED_ARTIFACT":
            return self._steps_corrupted_artifact(root, lkg_checkpoint)

        elif category == "INVALID_TRANSFORMATION":
            return self._steps_invalid_transformation(root, lkg_checkpoint)

        elif category == "DEPENDENCY_FAILURE":
            return self._steps_dependency_failure(root, lkg_checkpoint)

        elif category == "RESOURCE_FAILURE":
            return self._steps_resource_failure(root)

        elif category == "CONFIGURATION_FAILURE":
            return self._steps_configuration_failure(root)

        elif category == "DATA_QUALITY_FAILURE":
            return self._steps_data_quality_failure(root, lkg_checkpoint)

        elif category == "EXECUTION_ERROR":
            return self._steps_execution_error(root, lkg_checkpoint)

        elif category in ("TIMEOUT",):
            return self._steps_timeout(root)

        else:  # UNKNOWN / fallback
            return self._steps_unknown(root)

    # ── Individual step sequences ────────────────────────────────────────────

    def _steps_schema_mismatch(
        self, root: str | None, lkg: str | None
    ) -> list[RepairStep]:
        steps = []
        if root and lkg:
            steps.append(RepairStep(
                step_index=0,
                action_type=RepairActionType.REMAP_SCHEMA,
                target_node=root,
                target_artifact=None,
                reason=(
                    f"Apply schema remapping at node '{root}' to align "
                    f"output schema with downstream expectations."
                ),
                required_checkpoint=lkg,
                risk_level=RiskLevel.LOW,
                requires_validation=True,
            ))
            steps.append(RepairStep(
                step_index=1,
                action_type=RepairActionType.RERUN_FROM_CHECKPOINT,
                target_node=root,
                target_artifact=None,
                reason=(
                    f"Rerun from checkpoint preceding node '{root}' "
                    f"after schema fix."
                ),
                required_checkpoint=lkg,
                risk_level=RiskLevel.MEDIUM,
                requires_validation=True,
            ))
        else:
            steps.append(RepairStep(
                step_index=0,
                action_type=RepairActionType.MANUAL_REVIEW,
                target_node=root,
                target_artifact=None,
                reason=(
                    "Schema mismatch with no checkpoint available. "
                    "Manual schema inspection required."
                ),
                required_checkpoint=None,
                risk_level=RiskLevel.HIGH,
                requires_validation=False,
            ))
        return steps

    def _steps_missing_artifact(
        self, root: str | None, lkg: str | None
    ) -> list[RepairStep]:
        steps = []
        if lkg:
            steps.append(RepairStep(
                step_index=0,
                action_type=RepairActionType.RESTORE_CHECKPOINT,
                target_node=root,
                target_artifact=None,
                reason=(
                    f"Restore last-known-good checkpoint to recover "
                    f"missing artifact at '{root}'."
                ),
                required_checkpoint=lkg,
                risk_level=RiskLevel.MEDIUM,
                requires_validation=True,
            ))
        steps.append(RepairStep(
            step_index=len(steps),
            action_type=RepairActionType.REBUILD_ARTIFACT,
            target_node=root,
            target_artifact=None,
            reason=(
                f"Rebuild the missing artifact at node '{root}' "
                f"by re-executing the node."
            ),
            required_checkpoint=lkg,
            risk_level=RiskLevel.MEDIUM,
            requires_validation=True,
        ))
        return steps

    def _steps_corrupted_artifact(
        self, root: str | None, lkg: str | None
    ) -> list[RepairStep]:
        steps = []
        if lkg:
            steps.append(RepairStep(
                step_index=0,
                action_type=RepairActionType.RESTORE_CHECKPOINT,
                target_node=root,
                target_artifact=None,
                reason=(
                    f"Restore checkpoint before corrupted artifact at '{root}'."
                ),
                required_checkpoint=lkg,
                risk_level=RiskLevel.HIGH,
                requires_validation=True,
            ))
        steps.append(RepairStep(
            step_index=len(steps),
            action_type=RepairActionType.MANUAL_REVIEW,
            target_node=root,
            target_artifact=None,
            reason=(
                "Corrupted artifact detected. Manual inspection required "
                "to determine source of corruption before rebuilding."
            ),
            required_checkpoint=None,
            risk_level=RiskLevel.CRITICAL,
            requires_validation=False,
        ))
        return steps

    def _steps_invalid_transformation(
        self, root: str | None, lkg: str | None
    ) -> list[RepairStep]:
        steps = []
        steps.append(RepairStep(
            step_index=0,
            action_type=RepairActionType.USE_VALIDATED_PREPROCESSING,
            target_node=root,
            target_artifact=None,
            reason=(
                f"Apply the previously validated preprocessing configuration "
                f"at node '{root}' instead of the failing one."
            ),
            required_checkpoint=lkg,
            risk_level=RiskLevel.LOW,
            requires_validation=True,
        ))
        if lkg:
            steps.append(RepairStep(
                step_index=1,
                action_type=RepairActionType.RERUN_FROM_CHECKPOINT,
                target_node=root,
                target_artifact=None,
                reason=(
                    f"Rerun from checkpoint with corrected transformation."
                ),
                required_checkpoint=lkg,
                risk_level=RiskLevel.MEDIUM,
                requires_validation=True,
            ))
        return steps

    def _steps_dependency_failure(
        self, root: str | None, lkg: str | None
    ) -> list[RepairStep]:
        steps = []
        if lkg:
            steps.append(RepairStep(
                step_index=0,
                action_type=RepairActionType.RESTORE_CHECKPOINT,
                target_node=root,
                target_artifact=None,
                reason=(
                    f"Restore checkpoint to state before dependency failure "
                    f"at '{root}'."
                ),
                required_checkpoint=lkg,
                risk_level=RiskLevel.MEDIUM,
                requires_validation=True,
            ))
            steps.append(RepairStep(
                step_index=1,
                action_type=RepairActionType.RERUN_FROM_CHECKPOINT,
                target_node=root,
                target_artifact=None,
                reason=(
                    f"Rerun from root cause node '{root}' after restoring "
                    f"the checkpoint."
                ),
                required_checkpoint=lkg,
                risk_level=RiskLevel.MEDIUM,
                requires_validation=True,
            ))
        else:
            steps.append(RepairStep(
                step_index=0,
                action_type=RepairActionType.MANUAL_REVIEW,
                target_node=root,
                target_artifact=None,
                reason=(
                    "Dependency failure with no checkpoint. "
                    "Manual inspection of dependency chain required."
                ),
                required_checkpoint=None,
                risk_level=RiskLevel.HIGH,
                requires_validation=False,
            ))
        return steps

    def _steps_resource_failure(self, root: str | None) -> list[RepairStep]:
        return [
            RepairStep(
                step_index=0,
                action_type=RepairActionType.MANUAL_REVIEW,
                target_node=root,
                target_artifact=None,
                reason=(
                    f"Resource failure at '{root}'. Manual review of "
                    f"memory/CPU/disk constraints required before retry."
                ),
                required_checkpoint=None,
                risk_level=RiskLevel.HIGH,
                requires_validation=False,
            )
        ]

    def _steps_configuration_failure(self, root: str | None) -> list[RepairStep]:
        return [
            RepairStep(
                step_index=0,
                action_type=RepairActionType.RESTORE_CONFIGURATION,
                target_node=root,
                target_artifact=None,
                reason=(
                    f"Restore the last validated configuration for node '{root}'."
                ),
                required_checkpoint=None,
                risk_level=RiskLevel.MEDIUM,
                requires_validation=True,
            ),
            RepairStep(
                step_index=1,
                action_type=RepairActionType.RERUN_NODE,
                target_node=root,
                target_artifact=None,
                reason=(
                    f"Rerun node '{root}' with restored configuration."
                ),
                required_checkpoint=None,
                risk_level=RiskLevel.MEDIUM,
                requires_validation=True,
            ),
        ]

    def _steps_data_quality_failure(
        self, root: str | None, lkg: str | None
    ) -> list[RepairStep]:
        return [
            RepairStep(
                step_index=0,
                action_type=RepairActionType.USE_VALIDATED_PREPROCESSING,
                target_node=root,
                target_artifact=None,
                reason=(
                    f"Apply data quality guards and validated preprocessing "
                    f"at node '{root}'."
                ),
                required_checkpoint=lkg,
                risk_level=RiskLevel.LOW,
                requires_validation=True,
            ),
            RepairStep(
                step_index=1,
                action_type=RepairActionType.RERUN_NODE,
                target_node=root,
                target_artifact=None,
                reason=(
                    f"Rerun node '{root}' with data quality guards applied."
                ),
                required_checkpoint=lkg,
                risk_level=RiskLevel.MEDIUM,
                requires_validation=True,
            ),
        ]

    def _steps_execution_error(
        self, root: str | None, lkg: str | None
    ) -> list[RepairStep]:
        steps = []
        if lkg:
            steps.append(RepairStep(
                step_index=0,
                action_type=RepairActionType.RESTORE_CHECKPOINT,
                target_node=root,
                target_artifact=None,
                reason=(
                    f"Rollback to last-known-good checkpoint before "
                    f"execution failure at '{root}'."
                ),
                required_checkpoint=lkg,
                risk_level=RiskLevel.MEDIUM,
                requires_validation=True,
            ))
        steps.append(RepairStep(
            step_index=len(steps),
            action_type=RepairActionType.MANUAL_REVIEW,
            target_node=root,
            target_artifact=None,
            reason=(
                "Execution error requires manual inspection of the "
                "exception trace before automated rerun."
            ),
            required_checkpoint=None,
            risk_level=RiskLevel.HIGH,
            requires_validation=False,
        ))
        return steps

    def _steps_timeout(self, root: str | None) -> list[RepairStep]:
        return [
            RepairStep(
                step_index=0,
                action_type=RepairActionType.MANUAL_REVIEW,
                target_node=root,
                target_artifact=None,
                reason=(
                    f"Timeout at '{root}'. Review resource constraints "
                    f"and adjust timeout configuration before retry."
                ),
                required_checkpoint=None,
                risk_level=RiskLevel.MEDIUM,
                requires_validation=False,
            )
        ]

    def _steps_unknown(self, root: str | None) -> list[RepairStep]:
        return [
            RepairStep(
                step_index=0,
                action_type=RepairActionType.MANUAL_REVIEW,
                target_node=root,
                target_artifact=None,
                reason=(
                    "Unknown root cause. Human investigation required "
                    "before any automated repair is attempted."
                ),
                required_checkpoint=None,
                risk_level=RiskLevel.CRITICAL,
                requires_validation=False,
            )
        ]

    def _build_rationale(self, category: str, report: "RootCauseReport") -> str:
        return (
            f"RepairPlan for execution '{report.execution_id}'. "
            f"Primary hypothesis: {category} "
            f"(confidence={report.confidence:.2f}). "
            f"Root node: {report.root_node or 'unknown'}. "
            f"Steps ordered by risk (lowest first). "
            f"All steps require validation gate before continuing."
        )
