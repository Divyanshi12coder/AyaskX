"""
core/fault/localizer.py
-----------------------
Deterministic fault localization for AyaskX pipeline executions.

Distinguishes the OBSERVED failure node from the PROBABLE ROOT CAUSE node.
Evidence is gathered exclusively from supplied execution data and events.
Nothing is fabricated. Confidence is conservative.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.fault.models import FaultLocalization, FaultReport
from core.pipeline.status import NodeStatus

if TYPE_CHECKING:
    from core.observability.events import NodeEvent
    from core.pipeline.executor import NodeExecution, PipelineExecution


class FaultLocalizer:
    """
    Localizes the probable root cause of a pipeline fault.

    The key insight is that the OBSERVED failure node (where the exception
    was raised) is not necessarily the ROOT CAUSE.

    Example:
        A → B → C → D
        D raises KeyError, but C produced an invalid schema output.
        Observed node: D
        Probable root: C

    Confidence scoring
    ------------------
    Evidence quality is ranked as follows (highest → lowest confidence):

    Previous node status=FAILED                     → 0.90
    Output validation event for upstream node       → 0.85
    Output validation metadata for upstream node    → 0.85
    Missing checkpoint on upstream node             → 0.75
    No upstream evidence (only observed node)       → 0.55

    Confidence is capped at 0.95 for any single non-trivial evidence item.
    """

    def localize(
        self,
        execution: "PipelineExecution",
        fault: FaultReport,
        events: "tuple[NodeEvent, ...] | list[NodeEvent]" = (),
    ) -> FaultLocalization:
        """
        Return a FaultLocalization for the given fault.

        Parameters
        ----------
        execution : PipelineExecution
            The completed pipeline execution (failed or succeeded).
        fault : FaultReport
            The FaultReport produced by FaultDetector.detect().
        events : tuple/list of NodeEvent, optional
            Structured observability events emitted during execution.
            Used as additional evidence for localization.
        """

        # ------------------------------------------------------------------
        # RULE 1 — No fault: trivial localization
        # ------------------------------------------------------------------

        if not fault.detected:
            return FaultLocalization(
                execution_id=execution.execution_id,
                observed_node=None,
                probable_root_node=None,
                confidence=1.0,
                reasoning=(
                    "Pipeline completed successfully. "
                    "No fault localization required."
                ),
                evidence=(),
            )

        observed_node_id = fault.observed_node

        if observed_node_id is None:
            # Fault detected but no observed node recorded (unusual state).
            return FaultLocalization(
                execution_id=execution.execution_id,
                observed_node=None,
                probable_root_node=None,
                confidence=0.30,
                reasoning=(
                    "Fault was detected but no failed node was recorded. "
                    "Root cause cannot be determined."
                ),
                evidence=(
                    "fault_detected_without_node",
                ),
            )

        # ------------------------------------------------------------------
        # Build index of events by node_id for O(1) lookup
        # ------------------------------------------------------------------

        events_by_node: dict[str, list["NodeEvent"]] = {}
        for event in events:
            events_by_node.setdefault(event.node_id, []).append(event)

        # ------------------------------------------------------------------
        # Collect nodes that ran BEFORE the observed failed node
        # ------------------------------------------------------------------

        preceding_nodes: list["NodeExecution"] = []

        for node_exec in execution.nodes:
            if node_exec.node_id == observed_node_id:
                break
            preceding_nodes.append(node_exec)

        # ------------------------------------------------------------------
        # RULE 2 — Previous node has status=FAILED
        # ------------------------------------------------------------------
        # Walk in reverse (closest predecessor first = strongest causal link)

        for candidate in reversed(preceding_nodes):
            if candidate.status == NodeStatus.FAILED:
                collected_evidence = (
                    f"node '{candidate.node_id}' status=FAILED "
                    f"(error_type={candidate.error_type!r})",
                )
                return FaultLocalization(
                    execution_id=execution.execution_id,
                    observed_node=observed_node_id,
                    probable_root_node=candidate.node_id,
                    confidence=0.90,
                    reasoning=(
                        f"Preceding node '{candidate.node_id}' has status "
                        f"FAILED. This is the most direct upstream failure "
                        f"and is the probable root cause of the observed "
                        f"failure at '{observed_node_id}'."
                    ),
                    evidence=collected_evidence,
                )

        # ------------------------------------------------------------------
        # RULE 3 — Output validation event for an upstream node
        # ------------------------------------------------------------------

        for candidate in reversed(preceding_nodes):
            node_events = events_by_node.get(candidate.node_id, [])
            for event in node_events:
                if event.event_type == "output_validation_failed":
                    collected_evidence = (
                        f"event output_validation_failed for node "
                        f"'{candidate.node_id}' "
                        f"(event_type={event.event_type!r})",
                    )
                    return FaultLocalization(
                        execution_id=execution.execution_id,
                        observed_node=observed_node_id,
                        probable_root_node=candidate.node_id,
                        confidence=0.85,
                        reasoning=(
                            f"Observability event 'output_validation_failed' "
                            f"was recorded for preceding node "
                            f"'{candidate.node_id}'. This strongly suggests "
                            f"the root cause is upstream of the observed "
                            f"failure at '{observed_node_id}'."
                        ),
                        evidence=collected_evidence,
                    )

        # ------------------------------------------------------------------
        # RULE 4 — Output validation metadata for an upstream node
        # ------------------------------------------------------------------
        # Some pipelines store validation failure directly in output_metadata.

        for candidate in reversed(preceding_nodes):
            meta = candidate.output_metadata or {}
            # Look for explicit validation failure indicators in metadata
            validation_failed = (
                meta.get("validation_failed") is True
                or meta.get("output_validation") == "failed"
                or str(meta.get("validation_status", "")).lower() == "failed"
            )
            if validation_failed:
                collected_evidence = (
                    f"node '{candidate.node_id}' output_metadata "
                    f"indicates validation failure: {meta}",
                )
                return FaultLocalization(
                    execution_id=execution.execution_id,
                    observed_node=observed_node_id,
                    probable_root_node=candidate.node_id,
                    confidence=0.85,
                    reasoning=(
                        f"Preceding node '{candidate.node_id}' has "
                        f"output_metadata indicating output validation "
                        f"failure. This is the probable root cause of the "
                        f"observed failure at '{observed_node_id}'."
                    ),
                    evidence=collected_evidence,
                )

        # ------------------------------------------------------------------
        # RULE 5 — Missing checkpoint on upstream node (weaker evidence)
        # ------------------------------------------------------------------
        # If a successful node does not have a checkpoint_id when it should
        # (e.g., the executor always creates checkpoints after success), this
        # is a signal that something went wrong in that node's output
        # acceptance, even though it did not raise an exception.

        for candidate in reversed(preceding_nodes):
            if (
                candidate.status == NodeStatus.SUCCESS
                and candidate.checkpoint_id is None
            ):
                collected_evidence = (
                    f"node '{candidate.node_id}' succeeded but has "
                    f"no checkpoint_id (artifact may be invalid)",
                )
                return FaultLocalization(
                    execution_id=execution.execution_id,
                    observed_node=observed_node_id,
                    probable_root_node=candidate.node_id,
                    confidence=0.75,
                    reasoning=(
                        f"Preceding node '{candidate.node_id}' has status "
                        f"SUCCESS but no checkpoint_id was recorded. This "
                        f"suggests the node output may have been invalid or "
                        f"unpersisted, possibly causing the downstream "
                        f"failure at '{observed_node_id}'."
                    ),
                    evidence=collected_evidence,
                )

        # ------------------------------------------------------------------
        # RULE 6 — No upstream evidence: conservative localization
        # ------------------------------------------------------------------

        return FaultLocalization(
            execution_id=execution.execution_id,
            observed_node=observed_node_id,
            probable_root_node=observed_node_id,
            confidence=0.55,
            reasoning=(
                f"No upstream evidence was found to shift root cause away "
                f"from the observed failure node '{observed_node_id}'. "
                f"The observed node is the most likely root cause, but "
                f"confidence is conservative without further evidence."
            ),
            evidence=(
                f"only_evidence: node '{observed_node_id}' raised "
                f"the observed exception",
            ),
        )
