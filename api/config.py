"""
api/config.py
-------------
AyaskX API configuration — reads AYASKX_* environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


@dataclass
class Settings:
    checkpoint_root: Path = field(
        default_factory=lambda: Path(
            os.environ.get("AYASKX_CHECKPOINT_ROOT", ".ayask_checkpoints")
        )
    )
    artifact_root: Path = field(
        default_factory=lambda: Path(
            os.environ.get("AYASKX_ARTIFACT_ROOT", ".ayask_artifacts")
        )
    )
    upload_tmp_root: Path = field(
        default_factory=lambda: Path(
            os.environ.get("AYASKX_UPLOAD_TMP", ".ayask_uploads")
        )
    )
    audit_log_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get("AYASKX_AUDIT_LOG", ".ayask_audit.jsonl")
        )
    )
    store_root: Path = field(
        default_factory=lambda: Path(
            os.environ.get("AYASKX_STORE_ROOT", ".ayask_store")
        )
    )

    log_level: str = field(
        default_factory=lambda: os.environ.get("AYASKX_LOG_LEVEL", "INFO")
    )
    api_host: str = field(
        default_factory=lambda: os.environ.get("AYASKX_API_HOST", "0.0.0.0")
    )
    api_port: int = field(
        default_factory=lambda: int(os.environ.get("AYASKX_API_PORT", "8000"))
    )
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.environ.get("AYASKX_CORS_ORIGINS", "*").split(",")
            if o.strip()
        ]
    )
    max_upload_mb: int = field(
        default_factory=lambda: int(os.environ.get("AYASKX_MAX_UPLOAD_MB", "200"))
    )
    secret_key: str = field(
        default_factory=lambda: os.environ.get("AYASKX_SECRET_KEY", "")
    )

    def ensure_dirs(self) -> None:
        for d in (
            self.checkpoint_root,
            self.artifact_root,
            self.upload_tmp_root,
            self.store_root,
        ):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
