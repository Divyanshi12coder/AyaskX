"""
api/dependencies.py
--------------------
FastAPI dependency providers — shared singletons injected into routers.
Uses module-level globals instead of lru_cache to avoid hashability issues
with Settings dataclass.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from api.config import Settings, get_settings
from api.repositories.dataset_store import DatasetStore
from api.repositories.execution_store import ExecutionStore

# -------------------------------------------------------------------------
# Module-level singletons (initialized lazily on first request)
# -------------------------------------------------------------------------
_execution_store_singleton: ExecutionStore | None = None
_dataset_store_singleton: DatasetStore | None = None
_orchestrator_singleton = None
_audit_logger_singleton = None


def get_execution_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ExecutionStore:
    global _execution_store_singleton
    if _execution_store_singleton is None:
        _execution_store_singleton = ExecutionStore(settings.store_root)
    return _execution_store_singleton


def get_dataset_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> DatasetStore:
    global _dataset_store_singleton
    if _dataset_store_singleton is None:
        _dataset_store_singleton = DatasetStore(settings.store_root)
    return _dataset_store_singleton


def get_orchestrator(
    settings: Annotated[Settings, Depends(get_settings)],
):
    global _orchestrator_singleton
    if _orchestrator_singleton is None:
        from core.platform.orchestrator import AyaskXOrchestrator
        _orchestrator_singleton = AyaskXOrchestrator(
            checkpoint_root=settings.checkpoint_root,
            artifact_root=settings.artifact_root,
        )
    return _orchestrator_singleton


def get_audit_logger(
    settings: Annotated[Settings, Depends(get_settings)],
):
    global _audit_logger_singleton
    if _audit_logger_singleton is None:
        from core.security.audit import SecurityAuditLogger
        _audit_logger_singleton = SecurityAuditLogger(log_path=settings.audit_log_path)
    return _audit_logger_singleton


def reset_singletons() -> None:
    """Reset all singletons. For testing only."""
    global _execution_store_singleton, _dataset_store_singleton
    global _orchestrator_singleton, _audit_logger_singleton
    _execution_store_singleton = None
    _dataset_store_singleton = None
    _orchestrator_singleton = None
    _audit_logger_singleton = None
