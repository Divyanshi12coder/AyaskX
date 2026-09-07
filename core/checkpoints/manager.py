import hashlib
import json
from typing import Any

from core.checkpoints.models import Checkpoint
from core.pipeline.context import PipelineContext
from core.pipeline.node import PipelineNode


class CheckpointManager:
    """
    In-memory checkpoint manager.

    This is intentionally storage-agnostic.

    Later this can be backed by:
        PostgreSQL -> metadata
        MinIO/S3  -> artifacts

    without changing the pipeline-node contract.
    """

    def __init__(self):

        self._checkpoints: dict[
            str,
            Checkpoint,
        ] = {}

        self._artifacts: dict[
            str,
            Any,
        ] = {}

    # ----------------------------------------------------------
    # Create
    # ----------------------------------------------------------

    def create(
        self,
        node: PipelineNode,
        context: PipelineContext,
        artifact: Any,
        *,
        input_schema: dict | None = None,
        output_schema: dict | None = None,
        configuration: dict | None = None,
        dependency_versions: dict[str, str] | None = None,
        validation_status: str = "passed",
    ) -> Checkpoint:

        checkpoint_id = self._build_id(
            context.execution_id,
            node.node_id,
        )

        artifact_reference = (
            f"artifact://{checkpoint_id}"
        )

        data_hash = self._hash_artifact(
            artifact
        )

        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            execution_id=context.execution_id,
            pipeline_id=context.pipeline_id,
            node_id=node.node_id,
            node_version=node.version,
            artifact_reference=artifact_reference,
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            data_hash=data_hash,
            configuration=configuration or {},
            dependency_versions=(
                dependency_versions or {}
            ),
            validation_status=validation_status,
        )

        self._checkpoints[
            checkpoint_id
        ] = checkpoint

        self._artifacts[
            artifact_reference
        ] = artifact

        return checkpoint

    # ----------------------------------------------------------
    # Read
    # ----------------------------------------------------------

    def get(
        self,
        checkpoint_id: str,
    ) -> Checkpoint:

        if checkpoint_id not in self._checkpoints:

            raise KeyError(
                f"Checkpoint not found: "
                f"{checkpoint_id}"
            )

        return self._checkpoints[
            checkpoint_id
        ]

    def get_artifact(
        self,
        checkpoint_id: str,
    ) -> Any:

        checkpoint = self.get(
            checkpoint_id
        )

        reference = (
            checkpoint.artifact_reference
        )

        if reference is None:
            raise ValueError(
                "Checkpoint has no artifact reference."
            )

        return self._artifacts[
            reference
        ]

    # ----------------------------------------------------------
    # Recovery
    # ----------------------------------------------------------

    def last_known_good(
        self,
        execution_id: str,
    ) -> Checkpoint | None:

        candidates = [
            checkpoint
            for checkpoint
            in self._checkpoints.values()
            if (
                checkpoint.execution_id
                == execution_id
                and checkpoint.validation_status
                == "passed"
            )
        ]

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda checkpoint:
            checkpoint.created_at,
        )

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    @staticmethod
    def _build_id(
        execution_id: str,
        node_id: str,
    ) -> str:

        raw = (
            f"{execution_id}:{node_id}"
        )

        return hashlib.sha256(
            raw.encode("utf-8")
        ).hexdigest()[:16]

    @staticmethod
    def _hash_artifact(
        artifact: Any,
    ) -> str:

        try:

            serialized = json.dumps(
                artifact,
                sort_keys=True,
                default=str,
            )

        except TypeError:

            serialized = repr(artifact)

        return hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()