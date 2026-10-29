"""Conexão com o banco: SQLite no desenvolvimento, PostgreSQL em produção."""

from sqlalchemy import Engine, create_engine, event, inspect, text
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


# Colunas criadas depois da primeira versão. `create_all` só cria tabelas novas, então quem já
# tem o banco (ex.: o site no ar) ganha estas colunas na hora de iniciar.
NEW_COLUMNS = [
    ("images", "access_key", "VARCHAR(64)"),
    ("messages", "image_id", "INTEGER REFERENCES images(id) ON DELETE SET NULL"),
]


def add_missing_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, column, ddl in NEW_COLUMNS:
            if table not in tables:
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            if column not in existing:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
