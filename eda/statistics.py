from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class NumericStatistics:
    column: str
    count: int
    missing_count: int
    mean: float | None
    median: float | None
    std: float | None
    minimum: float | None
    maximum: float | None
    q1: float | None
    q3: float | None
    skewness: float | None
    zero_count: int
    negative_count: int
    outlier_count: int


@dataclass(frozen=True)
class CategoricalStatistics:
    column: str
    count: int
    missing_count: int
    unique_count: int
    most_frequent: str | None
    most_frequent_count: int
    most_frequent_fraction: float


@dataclass(frozen=True)
class StatisticalReport:
    numeric: tuple[NumericStatistics, ...]
    categorical: tuple[CategoricalStatistics, ...]
    constant_columns: tuple[str, ...]
    high_cardinality_columns: tuple[str, ...]
    warnings: tuple[str, ...]


class StatisticalAnalyzer:

    def analyze(
        self,
        df: pd.DataFrame,
    ) -> StatisticalReport:

        numeric_results = []
        categorical_results = []
        constant_columns = []
        high_cardinality_columns = []
        warnings = []

        for column in df.columns:

            series = df[column]

            # --------------------------------
            # Basic cardinality
            # --------------------------------

            unique_count_all = series.nunique(
                dropna=False
            )

            if unique_count_all <= 1:
                constant_columns.append(column)

            non_null_count = int(
                series.notna().sum()
            )

            unique_count = int(
                series.nunique(dropna=True)
            )

            if (
                non_null_count > 0
                and unique_count / non_null_count >= 0.95
            ):
                high_cardinality_columns.append(column)

            # --------------------------------
            # Boolean columns
            # Treat as categorical
            # --------------------------------

            if pd.api.types.is_bool_dtype(series):

                self._add_categorical_statistics(
                    column,
                    series,
                    categorical_results,
                )

                continue

            # --------------------------------
            # Numeric columns
            # --------------------------------

            if pd.api.types.is_numeric_dtype(series):

                numeric = pd.to_numeric(
                    series,
                    errors="coerce",
                ).dropna()

                if len(numeric) == 0:
                    continue

                q1 = float(
                    numeric.quantile(0.25)
                )

                q3 = float(
                    numeric.quantile(0.75)
                )

                iqr = q3 - q1

                lower = q1 - 1.5 * iqr
                upper = q3 + 1.5 * iqr

                outlier_count = int(
                    (
                        (numeric < lower)
                        | (numeric > upper)
                    ).sum()
                )

                skewness = numeric.skew()

                numeric_results.append(
                    NumericStatistics(
                        column=column,
                        count=int(numeric.count()),
                        missing_count=int(
                            series.isna().sum()
                        ),
                        mean=float(
                            numeric.mean()
                        ),
                        median=float(
                            numeric.median()
                        ),
                        std=(
                            float(numeric.std())
                            if len(numeric) > 1
                            else 0.0
                        ),
                        minimum=float(
                            numeric.min()
                        ),
                        maximum=float(
                            numeric.max()
                        ),
                        q1=q1,
                        q3=q3,
                        skewness=(
                            float(skewness)
                            if pd.notna(skewness)
                            else None
                        ),
                        zero_count=int(
                            (numeric == 0).sum()
                        ),
                        negative_count=int(
                            (numeric < 0).sum()
                        ),
                        outlier_count=outlier_count,
                    )
                )

                if outlier_count > 0:
                    warnings.append(
                        f"Potential outliers in "
                        f"{column}: {outlier_count}"
                    )

                continue

            # --------------------------------
            # Datetime
            # --------------------------------

            if pd.api.types.is_datetime64_any_dtype(
                series
            ):
                continue

            # --------------------------------
            # Categorical / text
            # --------------------------------

            if (
                pd.api.types.is_object_dtype(series)
                or isinstance(
                    series.dtype,
                    pd.CategoricalDtype,
                )
                or pd.api.types.is_string_dtype(series)
            ):

                self._add_categorical_statistics(
                    column,
                    series,
                    categorical_results,
                )

                continue

            # --------------------------------
            # Unsupported dtype
            # --------------------------------

            warnings.append(
                f"Unsupported dtype skipped: "
                f"{column} ({series.dtype})"
            )

        # --------------------------------
        # Global warnings
        # --------------------------------

        if constant_columns:
            warnings.append(
                "Constant columns detected: "
                + ", ".join(constant_columns)
            )

        if high_cardinality_columns:
            warnings.append(
                "High-cardinality columns detected: "
                + ", ".join(
                    high_cardinality_columns
                )
            )

        return StatisticalReport(
            numeric=tuple(numeric_results),
            categorical=tuple(categorical_results),
            constant_columns=tuple(
                constant_columns
            ),
            high_cardinality_columns=tuple(
                high_cardinality_columns
            ),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _add_categorical_statistics(
        column: str,
        series: pd.Series,
        output: list,
    ):

        non_null = series.dropna()

        missing_count = int(
            series.isna().sum()
        )

        if len(non_null) == 0:

            output.append(
                CategoricalStatistics(
                    column=column,
                    count=0,
                    missing_count=missing_count,
                    unique_count=0,
                    most_frequent=None,
                    most_frequent_count=0,
                    most_frequent_fraction=0.0,
                )
            )

            return

        frequencies = (
            non_null.value_counts()
        )

        most_frequent = frequencies.index[0]

        most_frequent_count = int(
            frequencies.iloc[0]
        )

        output.append(
            CategoricalStatistics(
                column=column,
                count=len(non_null),
                missing_count=missing_count,
                unique_count=int(
                    non_null.nunique()
                ),
                most_frequent=str(
                    most_frequent
                ),
                most_frequent_count=(
                    most_frequent_count
                ),
                most_frequent_fraction=(
                    most_frequent_count
                    / len(non_null)
                ),
            )
        )

    @staticmethod
    def to_dict(
        report: StatisticalReport,
    ) -> dict[str, Any]:

        return asdict(report)