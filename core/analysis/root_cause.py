"""
core/analysis/root_cause.py
----------------------------
Deterministic Root Cause Analyzer for AyaskX self-healing foundation.

Phase G: ROOT CAUSE ANALYSIS

Consumes:
    PipelineExecution
    FaultReport
    FaultLocalization
    NodeEvents (optional)

Produces:
    RootCauseReport — ranked hypotheses with bounded confidence, immutable.

Design principles:
- Deterministic evidence-first analysis.
- NO LLM calls.
- NO ML model calls.
- All confidence values are bounded and evidence-based.
- Evidence is never fabricated.
- Result is frozen (immutable).

Hypotheses ordered by confidence (descending).
Confidence is derived from the combination of:
    - fault type (strong signal)
    - localization confidence (amplifier)
    - observability events (corroboration)
    - checkpoint state (corroboration)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from core.fault.models import FaultLocalization, FaultReport, FaultSeverity, FaultType

if TYPE_CHECKING:
    from core.observability.events import NodeEvent
    from core.pipeline.executor import PipelineExecution


# ---------------------------------------------------------------------------
# HypothesisCategory
# ---------------------------------------------------------------------------


class HypothesisCategory:
    """String constants for root cause hypothesis categories."""

    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    MISSING_ARTIFACT = "MISSING_ARTIFACT"
    CORRUPTED_ARTIFACT = "CORRUPTED_ARTIFACT"
    INVALID_TRANSFORMATION = "INVALID_TRANSFORMATION"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    RESOURCE_FAILURE = "RESOURCE_FAILURE"
    CONFIGURATION_FAILURE = "CONFIGURATION_FAILURE"
    DATA_QUALITY_FAILURE = "DATA_QUALITY_FAILURE"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


# Fault-type → hypothesis category mapping (primary classification)
_FAULT_TO_HYPOTHESIS: dict[FaultType, str] = {
    FaultType.SCHEMA_MISMATCH: HypothesisCategory.SCHEMA_MISMATCH,
    FaultType.MISSING_ARTIFACT: HypothesisCategory.MISSING_ARTIFACT,
    FaultType.CORRUPTED_ARTIFACT: HypothesisCategory.CORRUPTED_ARTIFACT,
    FaultType.VALIDATION_ERROR: HypothesisCategory.INVALID_TRANSFORMATION,
    FaultType.DEPENDENCY_FAILURE: HypothesisCategory.DEPENDENCY_FAILURE,
    FaultType.RESOURCE_ERROR: HypothesisCategory.RESOURCE_FAILURE,
    FaultType.TIMEOUT: HypothesisCategory.TIMEOUT,
    FaultType.EXECUTION_ERROR: HypothesisCategory.EXECUTION_ERROR,
    FaultType.UNKNOWN: HypothesisCategory.UNKNOWN,
}

# Fault-type → plausible secondary hypotheses
_SECONDARY_HYPOTHESES: dict[FaultType, list[str]] = {
    FaultType.SCHEMA_MISMATCH: [
        HypothesisCategory.INVALID_TRANSFORMATION,
        HypothesisCategory.CONFIGURATION_FAILURE,
    ],
    FaultType.MISSING_ARTIFACT: [
        HypothesisCategory.DEPENDENCY_FAILURE,
        HypothesisCategory.INVALID_TRANSFORMATION,
    ],
    FaultType.CORRUPTED_ARTIFACT: [
        HypothesisCategory.DATA_QUALITY_FAILURE,
        HypothesisCategory.DEPENDENCY_FAILURE,
    ],
    FaultType.VALIDATION_ERROR: [
        HypothesisCategory.SCHEMA_MISMATCH,
        HypothesisCategory.DATA_QUALITY_FAILURE,
    ],
    FaultType.DEPENDENCY_FAILURE: [
        HypothesisCategory.MISSING_ARTIFACT,
        HypothesisCategory.CONFIGURATION_FAILURE,
    ],
    FaultType.EXECUTION_ERROR: [
        HypothesisCategory.DEPENDENCY_FAILURE,
        HypothesisCategory.CONFIGURATION_FAILURE,
        HypothesisCategory.RESOURCE_FAILURE,
    ],
    FaultType.RESOURCE_ERROR: [
        HypothesisCategory.TIMEOUT,
        HypothesisCategory.CONFIGURATION_FAILURE,
    ],
    FaultType.TIMEOUT: [
        HypothesisCategory.RESOURCE_FAILURE,
        HypothesisCategory.CONFIGURATION_FAILURE,
    ],
    FaultType.UNKNOWN: [
        HypothesisCategory.EXECUTION_ERROR,
        HypothesisCategory.CONFIGURATION_FAILURE,
    ],
}

# Recommended repair categories per hypothesis
_REPAIR_CATEGORIES: dict[str, tuple[str, ...]] = {
    HypothesisCategory.SCHEMA_MISMATCH: (
        "remap_schema",
        "rerun_from_transformation_node",
    ),
    HypothesisCategory.MISSING_ARTIFACT: (
        "restore_checkpoint",
        "rebuild_intermediate_artifact",
    ),
    HypothesisCategory.CORRUPTED_ARTIFACT: (
        "restore_checkpoint",
        "quarantine_artifact",
        "rebuild_intermediate_artifact",
    ),
    HypothesisCategory.INVALID_TRANSFORMATION: (
        "rerun_from_node",
        "use_validated_preprocessing_config",
    ),
    HypothesisCategory.DEPENDENCY_FAILURE: (
        "rerun_from_root_node",
        "restore_checkpoint",
    ),
    HypothesisCategory.RESOURCE_FAILURE: (
        "retry_with_reduced_load",
        "manual_review",
    ),
    HypothesisCategory.CONFIGURATION_FAILURE: (
        "restore_configuration",
        "manual_review",
    ),
    HypothesisCategory.DATA_QUALITY_FAILURE: (
        "rerun_preprocessing",
        "apply_data_quality_guard",
    ),
    HypothesisCategory.EXECUTION_ERROR: (
        "rollback_to_checkpoint",
        "rerun_from_node",
        "manual_review",
    ),
    HypothesisCategory.TIMEOUT: (
        "retry_with_reduced_load",
        "manual_review",
    ),
    HypothesisCategory.UNKNOWN: (
        "manual_review",
    ),
}


# ---------------------------------------------------------------------------
# Immutable result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RootCauseHypothesis:
    """
    A single ranked hypothesis about the root cause of a pipeline failure.

    Fields
    ------
    category           : HypothesisCategory constant
    confidence         : bounded [0.0, 0.95] (never claim certainty)
    explanation        : human-readable rationale
    evidence           : tuple of evidence strings (never fabricated)
    repair_categories  : tuple of recommended repair category strings
    """

    category: str
    confidence: float
    explanation: str
    evidence: tuple[str, ...]
    repair_categories: tuple[str, ...]


@dataclass(frozen=True)
class RootCauseReport:
    """
    Immutable root cause analysis result.

    Produced by RootCauseAnalyzer.analyze().

    Fields
    ------
    execution_id        : the pipeline execution under analysis
    root_node           : most probable root cause node (may be None)
    primary_fault_type  : FaultType constant from detector
    hypotheses          : ranked tuple of RootCauseHypothesis (descending confidence)
    confidence          : confidence in the top hypothesis
    evidence            : all collected evidence strings
    recommended_repair_categories : union of top-hypothesis repair categories
    analysed_at         : UTC timestamp
    """

    execution_id: str
    root_node: str | None
    primary_fault_type: str

    hypotheses: tuple[RootCauseHypothesis, ...]
    confidence: float

    evidence: tuple[str, ...]
    recommended_repair_categories: tuple[str, ...]

    analysed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def top_hypothesis(self) -> RootCauseHypothesis | None:
        return self.hypotheses[0] if self.hypotheses else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "root_node": self.root_node,
            "primary_fault_type": self.primary_fault_type,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "recommended_repair_categories": list(
                self.recommended_repair_categories
            ),
            "hypotheses": [
                {
                    "category": h.category,
                    "confidence": h.confidence,
                    "explanation": h.explanation,
                    "evidence": list(h.evidence),
                    "repair_categories": list(h.repair_categories),
                }
                for h in self.hypotheses
            ],
            "analysed_at": self.analysed_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# RootCauseAnalyzer
# ---------------------------------------------------------------------------


class RootCauseAnalyzer:
    """
    Deterministic, evidence-first root cause analyzer.

    Usage
    -----
    analyzer = RootCauseAnalyzer()
    report = analyzer.analyze(execution, fault, localization, events=events)

    The analyzer:
    - Never calls an LLM.
    - Never modifies any input.
    - Never fabricates evidence.
    - Bounds all confidence values.
    - Ranks hypotheses by confidence descending.
    """

    _MAX_CONFIDENCE = 0.95

    def analyze(
        self,
        execution: "PipelineExecution",
        fault: FaultReport,
        localization: FaultLocalization,
        events: tuple["NodeEvent", ...] = (),
    ) -> RootCauseReport:
        """
        Analyze a failed execution and produce a ranked RootCauseReport.

        Parameters
        ----------
        execution    : completed PipelineExecution
        fault        : FaultReport from FaultDetector
        localization : FaultLocalization from FaultLocalizer
        events       : observability events for corroboration
        """

        evidence: list[str] = []

        # ── Collect base evidence ────────────────────────────────────────────

        if fault.detected:
            evidence.append(
                f"fault_detected: type={fault.fault_type.value} "
                f"severity={fault.severity.value} "
                f"node={fault.observed_node}"
            )

        if localization.probable_root_node:
            evidence.append(
                f"localized_root: node={localization.probable_root_node} "
                f"confidence={localization.confidence:.2f}"
            )

        failed_node = execution.failed_node
        if failed_node:
            evidence.append(
                f"failed_node: id={failed_node.node_id} "
                f"error={failed_node.error_type}"
            )
            if failed_node.error_message:
                evidence.append(
                    f"error_message: {failed_node.error_message[:200]}"
                )

        last_success = execution.last_successful_node
        if last_success:
            evidence.append(
                f"last_success: node={last_success.node_id} "
                f"checkpoint={last_success.checkpoint_id}"
            )

        # ── Collect event evidence ───────────────────────────────────────────

        event_types_seen: set[str] = set()
        for event in events:
            event_types_seen.add(event.event_type)

        if "output_validation_failed" in event_types_seen:
            evidence.append("event_corroboration: output_validation_failed seen")

        if "node_failed" in event_types_seen:
            evidence.append("event_corroboration: node_failed event seen")

        # ── Build primary hypothesis ─────────────────────────────────────────

        primary_category = _FAULT_TO_HYPOTHESIS.get(
            fault.fault_type, HypothesisCategory.UNKNOWN
        )

        base_confidence = self._base_confidence(fault)
        loc_boost = self._localization_boost(localization)
        event_boost = 0.05 if event_types_seen else 0.0

        primary_confidence = min(
            base_confidence + loc_boost + event_boost,
            self._MAX_CONFIDENCE,
        )

        primary_evidence = tuple(evidence)
        primary_repair = _REPAIR_CATEGORIES.get(
            primary_category, ("manual_review",)
        )

        primary_hypothesis = RootCauseHypothesis(
            category=primary_category,
            confidence=primary_confidence,
            explanation=self._explain(
                category=primary_category,
                fault=fault,
                localization=localization,
            ),
            evidence=primary_evidence,
            repair_categories=primary_repair,
        )

        # ── Build secondary hypotheses ───────────────────────────────────────

        secondary_categories = _SECONDARY_HYPOTHESES.get(
            fault.fault_type, []
        )

        hypotheses: list[RootCauseHypothesis] = [primary_hypothesis]

        for i, cat in enumerate(secondary_categories):
            # Each secondary hypothesis gets a progressively lower confidence
            sec_confidence = min(
                primary_confidence * (0.60 - i * 0.10),
                self._MAX_CONFIDENCE,
            )
            sec_confidence = max(sec_confidence, 0.05)

            secondary_evidence: list[str] = []
            if evidence:
                secondary_evidence.append(evidence[0])  # fault_detected line
            secondary_evidence.append(
                f"secondary_hypothesis_rank: {i + 1}"
            )

            sec_repair = _REPAIR_CATEGORIES.get(cat, ("manual_review",))

            hypotheses.append(
                RootCauseHypothesis(
                    category=cat,
                    confidence=round(sec_confidence, 3),
                    explanation=self._explain_secondary(cat, fault),
                    evidence=tuple(secondary_evidence),
                    repair_categories=sec_repair,
                )
            )

        # ── Sort hypotheses by confidence descending ─────────────────────────

        hypotheses.sort(key=lambda h: h.confidence, reverse=True)

        top = hypotheses[0]

        return RootCauseReport(
            execution_id=execution.execution_id,
            root_node=localization.probable_root_node,
            primary_fault_type=fault.fault_type.value,
            hypotheses=tuple(hypotheses),
            confidence=top.confidence,
            evidence=tuple(evidence),
            recommended_repair_categories=top.repair_categories,
            analysed_at=datetime.now(timezone.utc),
        )

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _base_confidence(fault: FaultReport) -> float:
        """Base confidence derived from fault type determinism."""
        well_understood = {
            FaultType.SCHEMA_MISMATCH,
            FaultType.MISSING_ARTIFACT,
            FaultType.CORRUPTED_ARTIFACT,
            FaultType.VALIDATION_ERROR,
        }
        if fault.fault_type in well_understood:
            return 0.75
        if fault.fault_type in (FaultType.EXECUTION_ERROR,):
            return 0.55
        if fault.fault_type in (FaultType.DEPENDENCY_FAILURE,):
            return 0.60
        return 0.40

    @staticmethod
    def _localization_boost(localization: FaultLocalization) -> float:
        """Boost from a confident localization."""
        if localization.probable_root_node and localization.confidence >= 0.85:
            return 0.10
        if localization.probable_root_node and localization.confidence >= 0.60:
            return 0.05
        return 0.0

    @staticmethod
    def _explain(
        category: str,
        fault: FaultReport,
        localization: FaultLocalization,
    ) -> str:
        root = localization.probable_root_node or fault.observed_node or "unknown"
        base = {
            HypothesisCategory.SCHEMA_MISMATCH: (
                f"The schema of the output produced by node '{root}' does not match "
                f"what downstream nodes expect. This is the most likely cause of the "
                f"detected {fault.fault_type.value} fault."
            ),
            HypothesisCategory.MISSING_ARTIFACT: (
                f"An artifact required by node '{root}' or a downstream consumer "
                f"was not found. This can occur if a previous node failed to write "
                f"its output or if the artifact was deleted."
            ),
            HypothesisCategory.CORRUPTED_ARTIFACT: (
                f"An artifact at or produced by node '{root}' failed integrity "
                f"verification. This may indicate data corruption or a failed write."
            ),
            HypothesisCategory.INVALID_TRANSFORMATION: (
                f"Node '{root}' applied a transformation that produced invalid output. "
                f"This may indicate a preprocessing misconfiguration or a feature "
                f"engineering error."
            ),
            HypothesisCategory.DEPENDENCY_FAILURE: (
                f"A dependency of node '{root}' failed. The failure propagated to "
                f"downstream nodes. Root cause is likely upstream of the observed "
                f"failure point."
            ),
            HypothesisCategory.RESOURCE_FAILURE: (
                f"Node '{root}' encountered a resource constraint (memory, CPU, "
                f"disk) that caused the failure. Check resource availability."
            ),
            HypothesisCategory.CONFIGURATION_FAILURE: (
                f"Node '{root}' may have been misconfigured. Validate parameters, "
                f"environment variables, and external service connectivity."
            ),
            HypothesisCategory.DATA_QUALITY_FAILURE: (
                f"Input data at node '{root}' does not meet quality requirements. "
                f"Check for unexpected nulls, out-of-range values, or schema drift."
            ),
            HypothesisCategory.EXECUTION_ERROR: (
                f"Node '{root}' raised an unexpected exception during execution. "
                f"Inspect the error trace for the specific cause."
            ),
            HypothesisCategory.TIMEOUT: (
                f"Node '{root}' exceeded its time limit. Consider reducing workload "
                f"or increasing timeout configuration."
            ),
        }
        return base.get(
            category,
            f"Unclassified failure at node '{root}' — manual inspection required.",
        )

    @staticmethod
    def _explain_secondary(category: str, fault: FaultReport) -> str:
        return (
            f"Secondary hypothesis: the {fault.fault_type.value} fault "
            f"may also be explained by a {category} condition. "
            f"This is less likely than the primary hypothesis but should "
            f"be considered if primary repair steps fail."
        )
