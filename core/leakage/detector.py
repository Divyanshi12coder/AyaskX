from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class LeakageFinding:
    column: str
    risk: str
    reason: str


@dataclass(frozen=True)
class LeakageReport:
    target: str | None
    findings: tuple[LeakageFinding, ...]
    safe_features: tuple[str, ...]
    risky_features: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        risks = {finding.risk for finding in self.findings}
        risk = "high" if "high" in risks else "medium" if "medium" in risks else "none"
        return {
            "target": self.target,
            "leakage_risk": risk,
            "leaky_columns": list(self.risky_features),
            "safe_features": list(self.safe_features),
            "findings": [
                {"column": finding.column, "risk": finding.risk, "reason": finding.reason}
                for finding in self.findings
            ],
        }


class LeakageDetector:

    # Columns that commonly contain information
    # unavailable at prediction time.
    FUTURE_HINTS = {
        "future",
        "next",
        "actual",
        "outcome",
        "post",
        "after",
        "result",
    }

    # Direct target leakage.
    TARGET_DERIVED_HINTS = {
        "predicted",
        "prediction",
        "target",
    }

    ID_HINTS = {
        "id",
        "uuid",
        "key",
        "code",
    }

    def analyze(
        self,
        df: pd.DataFrame,
        target: str | None = None,
    ) -> LeakageReport:

        findings = []
        risky = []
        safe = []

        for column in df.columns:

            if column == target:
                continue

            name = column.lower()

            risk = None
            reason = None

            # --------------------------------
            # Explicit future / actual signals
            # --------------------------------

            for hint in self.FUTURE_HINTS:

                if hint in name:

                    risk = "high"

                    reason = (
                        f"Column name contains "
                        f"future/outcome indicator "
                        f"'{hint}'"
                    )

                    break

            # --------------------------------
            # Prediction-derived fields
            # --------------------------------

            if risk is None:

                for hint in self.TARGET_DERIVED_HINTS:

                    if hint in name:

                        risk = "high"

                        reason = (
                            f"Column appears to be "
                            f"model/target-derived: "
                            f"'{hint}'"
                        )

                        break

            # --------------------------------
            # Exact target-derived naming
            # --------------------------------

            if (
                risk is None
                and target is not None
            ):

                target_name = target.lower()

                if (
                    target_name in name
                    and column != target
                ):

                    risk = "high"

                    reason = (
                        "Column name contains "
                        "the target name"
                    )

            # --------------------------------
            # Identifier risk
            # --------------------------------

            if risk is None:

                if (
                    name.endswith("_id")
                    or name.endswith("_uuid")
                    or name.endswith("_key")
                    or name.endswith("_code")
                ):

                    risk = "medium"

                    reason = (
                        "Identifier-like column; "
                        "requires entity leakage review"
                    )

            # --------------------------------
            # Record finding
            # --------------------------------

            if risk is not None:

                findings.append(
                    LeakageFinding(
                        column=column,
                        risk=risk,
                        reason=reason,
                    )
                )

                risky.append(column)

            else:

                safe.append(column)

        return LeakageReport(
            target=target,
            findings=tuple(findings),
            safe_features=tuple(safe),
            risky_features=tuple(risky),
        )
