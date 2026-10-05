import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./data/symsoil.db")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def make_engine(url: str):
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 20} if url.startswith("sqlite") else {}, pool_pre_ping=True)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _):
            # SQLite's deferred read-to-write upgrade can fail immediately under
            # concurrent requests even with busy_timeout. Own BEGIN explicitly
            # and reserve the writer before reading mutable authorization/state.
            connection.isolation_level = None
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=20000")
        @event.listens_for(engine, "begin")
        def begin_sqlite(connection):
            connection.exec_driver_sql("BEGIN IMMEDIATE")
    return engine


def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
