"""Database helpers."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


def create_session_factory(database_url: str) -> tuple[Engine, sessionmaker[Session]]:
    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, future=True, expire_on_commit=False)

