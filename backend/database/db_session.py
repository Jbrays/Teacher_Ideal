from sqlalchemy import create_engine
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
    pool_recycle=600
)

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
    from . import models  # Importar modelos
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Base de datos inicializada")
    except Exception as e:
        logger.warning(f"⚠️ Advertencia: Error conectando a la base de datos en el arranque. El servidor iniciará, pero las operaciones a DB fallarán: {e}", exc_info=True)
