from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import logging

logger = logging.getLogger(__name__)

# Configuración estricta para la nube (Neon PostgreSQL)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("⚠️ ERROR CRÍTICO: La variable de entorno 'DATABASE_URL' no está configurada. El sistema solo puede ejecutarse en la nube con Neon PostgreSQL.")

# Crear engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=600,
    pool_reset_on_return="rollback",
)


@event.listens_for(engine, "connect")
def _force_read_write_transactions(dbapi_connection, _connection_record):
    """Evita heredar sesiones read-only desde un endpoint PostgreSQL pooler."""
    if hasattr(dbapi_connection, "set_session"):
        dbapi_connection.set_session(readonly=False)

# Crear SessionLocal
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para los modelos
Base = declarative_base()

# Dependency para FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Crear todas las tablas
def init_db():
    from . import models
    from .schema_migrations import migrate_database_schema

    assert models
    migrate_database_schema(engine, Base.metadata)
    logger.info("Base de datos inicializada")
