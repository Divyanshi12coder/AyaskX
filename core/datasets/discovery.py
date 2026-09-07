from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class DatasetCandidate:
    path: str
    rows: int
    columns: int
    column_names: tuple[str, ...]


@dataclass(frozen=True)
class DatasetDiscoveryResult:
    datasets: tuple[DatasetCandidate, ...]


class DatasetDiscovery:
    """
    Discovers tabular datasets without making assumptions about
    a particular ML model or dataset.

    This is intentionally a discovery layer only.
    Profiling, target detection and task detection remain separate
    responsibilities.
    """

    SUPPORTED_EXTENSIONS = {".csv"}

    def discover(
        self,
        root: str | Path,
        recursive: bool = True,
    ) -> DatasetDiscoveryResult:

        root = Path(root)

        if not root.exists():
            raise FileNotFoundError(
                f"Dataset directory not found: {root}"
            )

        if not root.is_dir():
            raise ValueError(
                f"Dataset path is not a directory: {root}"
            )

        if recursive:
            files = sorted(
                path
                for path in root.rglob("*")
                if (
                    path.is_file()
                    and path.suffix.lower()
                    in self.SUPPORTED_EXTENSIONS
                )
            )
        else:
            files = sorted(
                path
                for path in root.iterdir()
                if (
                    path.is_file()
                    and path.suffix.lower()
                    in self.SUPPORTED_EXTENSIONS
                )
            )

        candidates: list[DatasetCandidate] = []

        for path in files:

            try:
                df = pd.read_csv(path)

            except Exception:
                # A discovery failure for one file should not
                # prevent discovery of all other datasets.
                continue

            candidates.append(
                DatasetCandidate(
                    path=str(path),
                    rows=len(df),
                    columns=len(df.columns),
                    column_names=tuple(
                        str(column)
                        for column in df.columns
                    ),
                )
            )

        return DatasetDiscoveryResult(
            datasets=tuple(candidates)
        )