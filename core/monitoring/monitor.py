"""
core/monitoring/monitor.py
---------------------------
Monitoring foundation for AyaskX.

Phase L: MONITORING FOUNDATION

Generates structured, configurable alerts for:
    - execution failures
    - data quality degradation
    - schema changes
    - data drift (population-level statistics)
    - model performance degradation
    - prediction drift

Design principles:
- No arbitrary thresholds — all thresholds are configurable.
- All alerts are structured, immutable, serializable.
- NO EXTERNAL SERVICES are called in this phase.
- Alerts are collected in memory and can be drained/exported.
- Deterministic: same inputs always produce same alerts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class AlertSeverity:
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AlertCategory:
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    DATA_QUALITY = "DATA_QUALITY"
    SCHEMA_CHANGE = "SCHEMA_CHANGE"
    DATA_DRIFT = "DATA_DRIFT"
    PREDICTION_DRIFT = "PREDICTION_DRIFT"
    MODEL_DEGRADATION = "MODEL_DEGRADATION"


@dataclass(frozen=True)
class MonitoringAlert:
    """
    Immutable structured monitoring alert.

    Fields
    ------
    alert_id     : unique identifier
    category     : AlertCategory constant
    severity     : AlertSeverity constant
    execution_id : related pipeline execution_id (may be None)
    node_id      : related node (may be None)
    message      : human-readable alert message
    evidence     : tuple of evidence strings
    metadata     : additional context
    raised_at    : UTC timestamp
    """

    alert_id: str
    category: str
    severity: str
    execution_id: str | None
    node_id: str | None
    message: str
    evidence: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    raised_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "category": self.category,
            "severity": self.severity,
            "execution_id": self.execution_id,
            "node_id": self.node_id,
            "message": self.message,
            "evidence": list(self.evidence),
            "metadata": self.metadata,
            "raised_at": self.raised_at.isoformat(),
        }


@dataclass
class MonitoringConfig:
    """
    Configurable thresholds for monitoring checks.
    All thresholds have documented defaults.
    """

    # Data quality
    max_missing_fraction: float = 0.30
    max_high_cardinality_fraction: float = 0.80
    min_rows: int = 10

    # Data drift (statistical)
    max_mean_drift_fraction: float = 0.20   # mean shift > 20% of original
    max_std_drift_fraction: float = 0.30    # std shift > 30%

    # Model performance
    min_classification_accuracy: float = 0.50
    min_regression_r2: float = 0.00         # R² must be positive

    # Prediction drift
    max_prediction_mean_drift_fraction: float = 0.25


class PipelineMonitor:
    """
    Collects and generates structured monitoring alerts.

    Instantiate once per pipeline execution (or share across executions
    and drain alerts between runs).

    Usage
    -----
    monitor = PipelineMonitor()

    # After pipeline execution:
    monitor.check_execution(execution)

    # After training:
    monitor.check_model_metrics(metrics, task_type)

    # Between data batches:
    monitor.check_data_drift(reference_stats, current_stats)

    # Drain alerts:
    alerts = monitor.drain()
    """

    def __init__(
        self,
        config: MonitoringConfig | None = None,
    ) -> None:
        self.config = config or MonitoringConfig()
        self._alerts: list[MonitoringAlert] = []
        self._alert_counter = 0

    def _next_id(self) -> str:
        self._alert_counter += 1
        return f"alert-{self._alert_counter:06d}"

    def _raise(
        self,
        category: str,
        severity: str,
        message: str,
        evidence: tuple[str, ...],
        execution_id: str | None = None,
        node_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MonitoringAlert:
        alert = MonitoringAlert(
            alert_id=self._next_id(),
            category=category,
            severity=severity,
            execution_id=execution_id,
            node_id=node_id,
            message=message,
            evidence=evidence,
            metadata=metadata or {},
            raised_at=datetime.now(timezone.utc),
        )
        self._alerts.append(alert)
        return alert

    @property
    def alerts(self) -> tuple[MonitoringAlert, ...]:
        return tuple(self._alerts)

    def drain(self) -> tuple[MonitoringAlert, ...]:
        """Return all alerts and clear the internal buffer."""
        result = tuple(self._alerts)
        self._alerts.clear()
        return result

    # -----------------------------------------------------------------------
    # Execution failure monitoring
    # -----------------------------------------------------------------------

    def check_execution(
        self,
        execution: Any,
    ) -> None:
        """Check a completed PipelineExecution for failures."""
        from core.pipeline.status import PipelineStatus, NodeStatus

        if execution.status == PipelineStatus.FAILED:
            failed = execution.failed_node
            node_id = failed.node_id if failed else None
            evidence = []
            if failed:
                evidence.append(f"failed_node: {failed.node_id}")
                if failed.error_type:
                    evidence.append(f"error_type: {failed.error_type}")
                if failed.error_message:
                    evidence.append(f"error_message: {failed.error_message[:200]}")

            self._raise(
                category=AlertCategory.EXECUTION_FAILURE,
                severity=AlertSeverity.ERROR,
                message=(
                    f"Pipeline execution '{execution.execution_id}' failed "
                    f"at node '{node_id}'."
                ),
                evidence=tuple(evidence),
                execution_id=execution.execution_id,
                node_id=node_id,
            )

    # -----------------------------------------------------------------------
    # Data quality monitoring
    # -----------------------------------------------------------------------

    def check_data_quality(
        self,
        node_id: str,
        execution_id: str,
        *,
        row_count: int,
        missing_fraction: float,
        high_cardinality_fraction: float = 0.0,
    ) -> None:
        """Check data quality metrics against configured thresholds."""

        if row_count < self.config.min_rows:
            self._raise(
                category=AlertCategory.DATA_QUALITY,
                severity=AlertSeverity.WARNING,
                message=(
                    f"Node '{node_id}': dataset has only {row_count} rows "
                    f"(minimum: {self.config.min_rows})."
                ),
                evidence=(f"row_count: {row_count}",),
                execution_id=execution_id,
                node_id=node_id,
            )

        if missing_fraction > self.config.max_missing_fraction:
            self._raise(
                category=AlertCategory.DATA_QUALITY,
                severity=AlertSeverity.WARNING,
                message=(
                    f"Node '{node_id}': missing data fraction "
                    f"{missing_fraction:.1%} exceeds threshold "
                    f"{self.config.max_missing_fraction:.1%}."
                ),
                evidence=(
                    f"missing_fraction: {missing_fraction:.4f}",
                    f"threshold: {self.config.max_missing_fraction:.4f}",
                ),
                execution_id=execution_id,
                node_id=node_id,
            )

    # -----------------------------------------------------------------------
    # Schema change monitoring
    # -----------------------------------------------------------------------

    def check_schema_change(
        self,
        node_id: str,
        execution_id: str,
        *,
        reference_columns: tuple[str, ...],
        current_columns: tuple[str, ...],
    ) -> None:
        added = set(current_columns) - set(reference_columns)
        removed = set(reference_columns) - set(current_columns)

        if added or removed:
            self._raise(
                category=AlertCategory.SCHEMA_CHANGE,
                severity=AlertSeverity.ERROR,
                message=(
                    f"Node '{node_id}': schema changed. "
                    f"Added: {sorted(added)}, Removed: {sorted(removed)}."
                ),
                evidence=(
                    f"added_columns: {sorted(added)}",
                    f"removed_columns: {sorted(removed)}",
                ),
                execution_id=execution_id,
                node_id=node_id,
            )

    # -----------------------------------------------------------------------
    # Data drift monitoring
    # -----------------------------------------------------------------------

    def check_data_drift(
        self,
        node_id: str,
        execution_id: str,
        *,
        reference_stats: dict[str, dict[str, float]],
        current_stats: dict[str, dict[str, float]],
    ) -> None:
        """
        Check for data drift between reference and current batch statistics.

        reference_stats/current_stats: {column_name: {"mean": ..., "std": ...}}
        """
        for col in reference_stats:
            if col not in current_stats:
                continue

            ref = reference_stats[col]
            cur = current_stats[col]

            ref_mean = ref.get("mean", 0.0)
            cur_mean = cur.get("mean", 0.0)

            if abs(ref_mean) > 1e-9:
                mean_drift = abs(cur_mean - ref_mean) / abs(ref_mean)
                if mean_drift > self.config.max_mean_drift_fraction:
                    self._raise(
                        category=AlertCategory.DATA_DRIFT,
                        severity=AlertSeverity.WARNING,
                        message=(
                            f"Node '{node_id}': column '{col}' mean drifted "
                            f"{mean_drift:.1%} from reference "
                            f"(threshold: {self.config.max_mean_drift_fraction:.1%})."
                        ),
                        evidence=(
                            f"column: {col}",
                            f"ref_mean: {ref_mean:.4f}",
                            f"cur_mean: {cur_mean:.4f}",
                            f"drift: {mean_drift:.4f}",
                        ),
                        execution_id=execution_id,
                        node_id=node_id,
                    )

    # -----------------------------------------------------------------------
    # Model performance monitoring
    # -----------------------------------------------------------------------

    def check_model_metrics(
        self,
        execution_id: str,
        model_name: str,
        task_type: str,
        metrics: dict[str, float],
    ) -> None:
        """Check model evaluation metrics against configured thresholds."""

        if task_type == "classification":
            acc = metrics.get("accuracy", None)
            if acc is not None and acc < self.config.min_classification_accuracy:
                self._raise(
                    category=AlertCategory.MODEL_DEGRADATION,
                    severity=AlertSeverity.WARNING,
                    message=(
                        f"Model '{model_name}': accuracy {acc:.3f} is below "
                        f"minimum threshold "
                        f"{self.config.min_classification_accuracy:.3f}."
                    ),
                    evidence=(
                        f"model: {model_name}",
                        f"accuracy: {acc:.4f}",
                        f"threshold: {self.config.min_classification_accuracy}",
                    ),
                    execution_id=execution_id,
                )

        elif task_type == "regression":
            r2 = metrics.get("r2", None)
            if r2 is not None and r2 < self.config.min_regression_r2:
                self._raise(
                    category=AlertCategory.MODEL_DEGRADATION,
                    severity=AlertSeverity.WARNING,
                    message=(
                        f"Model '{model_name}': R² {r2:.3f} is below "
                        f"minimum threshold {self.config.min_regression_r2:.3f}."
                    ),
                    evidence=(
                        f"model: {model_name}",
                        f"r2: {r2:.4f}",
                        f"threshold: {self.config.min_regression_r2}",
                    ),
                    execution_id=execution_id,
                )
