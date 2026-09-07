from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any
import hashlib
import json
from pathlib import Path
from uuid import uuid4


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    execution_id: str
    node_id: str

    created_at: datetime

    node_version: str
    data_hash: str

    input_schema: dict[str, Any]
    output_schema: dict[str, Any]

    artifact_path: str | None
    validation_status: str

    metadata: dict[str, Any]


class CheckpointManager:
    """
    Manages last-known-good pipeline checkpoints.

    The manager stores metadata separately from artifacts.

    It does not automatically restore or overwrite production state.
    Recovery will be handled by a future recovery engine.
    """

    def __init__(
        self,
        root_dir: str | Path = ".ayask_checkpoints",
    ) -> None:

        self.root_dir = Path(root_dir)

        self.root_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._checkpoints: dict[str, Checkpoint] = {}

    # ---------------------------------------------------------
    # CREATE
    # ---------------------------------------------------------

    def create(
        self,
        *,
        execution_id: str,
        node_id: str,
        artifact: Any = None,
        node_version: str = "unknown",
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        validation_status: str = "passed",
        metadata: dict[str, Any] | None = None,
    ) -> Checkpoint:

        checkpoint_id = str(uuid4())

        data_hash = self._hash_artifact(
            artifact
        )

        artifact_path = None

        if artifact is not None:
            artifact_path = self._store_artifact(
                checkpoint_id,
                artifact,
            )

        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            execution_id=execution_id,
            node_id=node_id,
            created_at=_utc_now(),
            node_version=node_version,
            data_hash=data_hash,
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            artifact_path=artifact_path,
            validation_status=validation_status,
            metadata=metadata or {},
        )

        self._checkpoints[
            checkpoint_id
        ] = checkpoint

        self._persist_metadata(
            checkpoint
        )

        return checkpoint

    # ---------------------------------------------------------
    # LOOKUP
    # ---------------------------------------------------------

    def get(
        self,
        checkpoint_id: str,
    ) -> Checkpoint | None:

        return self._checkpoints.get(
            checkpoint_id
        )

    def list(
        self,
    ) -> tuple[Checkpoint, ...]:

        return tuple(
            self._checkpoints.values()
        )

    # ---------------------------------------------------------
    # LAST KNOWN GOOD
    # ---------------------------------------------------------

    def last_known_good(
        self,
        execution_id: str | None = None,
    ) -> Checkpoint | None:

        candidates = [
            checkpoint
            for checkpoint
            in self._checkpoints.values()
            if checkpoint.validation_status == "passed"
        ]

        if execution_id is not None:
            candidates = [
                checkpoint
                for checkpoint in candidates
                if checkpoint.execution_id
                == execution_id
            ]

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda checkpoint:
                checkpoint.created_at,
        )

    # ---------------------------------------------------------
    # ARTIFACT RESTORE
    # ---------------------------------------------------------

    def restore(
        self,
        checkpoint_id: str,
    ) -> Any:

        checkpoint = self.get(
            checkpoint_id
        )

        if checkpoint is None:
            raise KeyError(
                f"Checkpoint not found: "
                f"{checkpoint_id}"
            )

        if checkpoint.artifact_path is None:
            return None

        path = Path(
            checkpoint.artifact_path
        )

        if not path.exists():
            raise FileNotFoundError(
                f"Checkpoint artifact missing: "
                f"{path}"
            )

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            payload = json.load(file)

        return payload

    # ---------------------------------------------------------
    # HASHING
    # ---------------------------------------------------------

    @staticmethod
    def _hash_artifact(
        artifact: Any,
    ) -> str:

        if artifact is None:
            return ""

        payload = CheckpointManager._serialize(
            artifact
        )

        return hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _serialize(
        artifact: Any,
    ) -> str:

        if isinstance(
            artifact,
            (dict, list, tuple, str, int, float, bool),
        ):
            try:
                return json.dumps(
                    artifact,
                    sort_keys=True,
                    default=str,
                )
            except TypeError:
                pass

        # pandas-like objects
        to_dict = getattr(
            artifact,
            "to_dict",
            None,
        )

        if callable(to_dict):
            return json.dumps(
                to_dict(),
                sort_keys=True,
                default=str,
            )

        return repr(artifact)

    # ---------------------------------------------------------
    # STORAGE
    # ---------------------------------------------------------

    def _store_artifact(
        self,
        checkpoint_id: str,
        artifact: Any,
    ) -> str:

        path = (
            self.root_dir
            / f"{checkpoint_id}.json"
        )

        payload = self._serialize(
            artifact
        )

        # Validate that we actually have
        # JSON-compatible persisted data.
        parsed = json.loads(
            payload
        )

        with path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                parsed,
                file,
                indent=2,
                default=str,
            )

        return str(
            path.resolve()
        )

    def _persist_metadata(
        self,
        checkpoint: Checkpoint,
    ) -> None:

        path = (
            self.root_dir
            / f"{checkpoint.checkpoint_id}.metadata.json"
        )

        payload = asdict(
            checkpoint
        )

        payload["created_at"] = (
            checkpoint.created_at.isoformat()
        )

        with path.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                payload,
                file,
                indent=2,
                default=str,
            )