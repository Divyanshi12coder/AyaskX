from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd

from eda.profiler import DatasetProfiler
from eda.statistics import StatisticalAnalyzer


DATA_DIR = Path("source_friend_v1")
OUTPUT_DIR = Path("artifacts/eda")

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def main():

    profiler = DatasetProfiler()
    analyzer = StatisticalAnalyzer()

    csv_files = sorted(
        DATA_DIR.rglob("*.csv")
    )

    if not csv_files:
        print(
            f"No CSV files found in: {DATA_DIR}"
        )
        return

    print(
        f"\nFound {len(csv_files)} CSV files\n"
    )

    summary = []

    for csv_file in csv_files:

        print("=" * 70)
        print(f"FILE: {csv_file}")
        print("=" * 70)

        try:
            df = pd.read_csv(csv_file)

        except Exception as exc:
            print(f"READ ERROR: {exc}")
            continue

        profile = profiler.profile(df)
        statistics = analyzer.analyze(df)

        print(
            f"Rows       : {profile.rows}"
        )

        print(
            f"Columns    : {profile.column_count}"
        )

        print(
            f"Numeric    : "
            f"{len(profile.numeric_columns)}"
        )

        print(
            f"Categorical: "
            f"{len(profile.categorical_columns)}"
        )

        print(
            f"Datetime   : "
            f"{len(profile.datetime_candidates)}"
        )

        print(
            f"Spatial    : "
            f"{len(profile.spatial_candidates)}"
        )

        print(
            f"Identifiers: "
            f"{len(profile.identifier_candidates)}"
        )

        print(
            f"Constants  : "
            f"{len(statistics.constant_columns)}"
        )

        print(
            f"High-card.: "
            f"{len(statistics.high_cardinality_columns)}"
        )

        if profile.warnings:
            print("\nProfiler warnings:")

            for warning in profile.warnings:
                print(f"  - {warning}")

        if statistics.warnings:
            print("\nStatistical warnings:")

            for warning in statistics.warnings:
                print(f"  - {warning}")

        print("\nColumns:")

        for column in profile.column_profiles:

            print(
                f"  {column.name:30} "
                f"{column.semantic_type:12} "
                f"missing={column.missing_fraction:.1%}"
            )

        summary.append(
            {
                "file": str(csv_file),
                "rows": profile.rows,
                "columns": profile.column_count,
                "numeric": len(
                    profile.numeric_columns
                ),
                "categorical": len(
                    profile.categorical_columns
                ),
                "datetime": len(
                    profile.datetime_candidates
                ),
                "spatial": len(
                    profile.spatial_candidates
                ),
                "identifiers": len(
                    profile.identifier_candidates
                ),
                "constant": len(
                    statistics.constant_columns
                ),
                "high_cardinality": len(
                    statistics.high_cardinality_columns
                ),
            }
        )

    summary_df = pd.DataFrame(summary)

    output_file = (
        OUTPUT_DIR
        / "friend_dataset_summary.csv"
    )

    summary_df.to_csv(
        output_file,
        index=False,
    )

    print("\n")
    print("=" * 70)
    print("PROFILE COMPLETE")
    print("=" * 70)
    print(
        f"Summary saved to: {output_file}"
    )


if __name__ == "__main__":
    main()