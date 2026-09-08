from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def _database_url() -> str:
    return os.getenv(
        "AYASKX_DATABASE_URL",
        "sqlite:///./ayaskx.db",
    )


DATABASE_URL = _database_url()

_connect_args = (
    {"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def init_db() -> None:
    # Import models before create_all so SQLAlchemy knows
    # about every registered table.
    from core.database import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_session():
    return SessionLocal()


def database_exists() -> bool:
    if not DATABASE_URL.startswith("sqlite:///"):
        return True

    raw_path = DATABASE_URL.removeprefix("sqlite:///")

    if raw_path == ":memory:":
        return True

    return Path(raw_path).exists()