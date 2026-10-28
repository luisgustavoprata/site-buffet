"""Conexão com o banco: SQLite no desenvolvimento, PostgreSQL em produção."""

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    if not url.startswith("sqlite"):
        return create_engine(url, pool_pre_ping=True)

    options: dict = {"connect_args": {"check_same_thread": False}}
    if ":memory:" in url or url in {"sqlite://", "sqlite:///"}:
        options["poolclass"] = StaticPool  # o mesmo banco em memória para todas as conexões
    engine = create_engine(url, **options)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record) -> None:
        # O SQLite só respeita chaves estrangeiras (e o ON DELETE CASCADE) com isto ligado.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine
