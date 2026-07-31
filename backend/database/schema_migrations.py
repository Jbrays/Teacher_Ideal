"""Migraciones aditivas mínimas para esquemas creados antes del catálogo v3."""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import MetaData


logger = logging.getLogger(__name__)


_NODO_COLUMNS = {
    "source": {
        "postgresql": "VARCHAR",
        "sqlite": "VARCHAR",
    },
    "source_version": {
        "postgresql": "VARCHAR",
        "sqlite": "VARCHAR",
    },
    "external_id": {
        "postgresql": "TEXT",
        "sqlite": "TEXT",
    },
    "external_url": {
        "postgresql": "TEXT",
        "sqlite": "TEXT",
    },
    "description": {
        "postgresql": "TEXT",
        "sqlite": "TEXT",
    },
    "kind": {
        "postgresql": "VARCHAR NOT NULL DEFAULT 'concept'",
        "sqlite": "VARCHAR NOT NULL DEFAULT 'concept'",
    },
    "labels": {
        "postgresql": "JSON NOT NULL DEFAULT '{}'::json",
        "sqlite": "JSON NOT NULL DEFAULT '{}'",
    },
    "embedding_enabled": {
        "postgresql": "BOOLEAN NOT NULL DEFAULT TRUE",
        "sqlite": "BOOLEAN NOT NULL DEFAULT 1",
    },
    "source_attributes": {
        "postgresql": "JSON NOT NULL DEFAULT '{}'::json",
        "sqlite": "JSON NOT NULL DEFAULT '{}'",
    },
}


def _add_legacy_nodo_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if "nodos" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("nodos")}
    dialect = engine.dialect.name
    if dialect not in {"postgresql", "sqlite"}:
        raise RuntimeError(
            f"Migración del catálogo no implementada para {dialect}."
        )

    statements = [
        text(f"ALTER TABLE nodos ADD COLUMN {name} {definition[dialect]}")
        for name, definition in _NODO_COLUMNS.items()
        if name not in existing
    ]
    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(statement)
    logger.info(
        "Esquema legado de nodos actualizado con %s columnas.",
        len(statements),
    )


def _ensure_catalog_indexes(engine: Engine) -> None:
    if "nodos" not in inspect(engine).get_table_names():
        return
    with engine.begin() as connection:
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_nodos_source ON nodos (source)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_nodos_kind ON nodos (kind)")
        )


def migrate_database_schema(engine: Engine, metadata: MetaData) -> None:
    """
    Lleva una base existente al esquema actual sin eliminar filas.

    Primero amplía ``nodos`` cuando proviene del catálogo antiguo; luego
    ``create_all`` puede crear tablas nuevas como ``nodo_relaciones``.
    """
    _add_legacy_nodo_columns(engine)
    metadata.create_all(bind=engine)
    _ensure_catalog_indexes(engine)
