"""
Configuración centralizada del sistema.

Todas las variables de entorno se leen una sola vez aquí.
Ningún otro módulo debe llamar directamente a os.getenv salvo para valores
específicos de una librería de terceros.
"""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuración global del backend."""

    # Base de datos
    database_url: str = Field(..., validation_alias="DATABASE_URL")

    # Google Cloud / Vertex AI
    google_cloud_project: str = Field(..., validation_alias="GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = Field("global", validation_alias="GOOGLE_CLOUD_LOCATION")
    google_application_credentials: Optional[str] = Field(None, validation_alias="GOOGLE_APPLICATION_CREDENTIALS")

    # Modelos Gemini
    gemini_model_name: str = Field("gemini-3.1-flash-lite", validation_alias="GEMINI_MODEL_NAME")

    # Firebase
    firebase_credentials_path: Optional[str] = Field(None, validation_alias="FIREBASE_CREDENTIALS_PATH")
    cors_origins: str = Field("", validation_alias="CORS_ORIGINS")

    # Cache y taxonomía
    fuzzy_threshold: float = Field(0.93, validation_alias="FUZZY_THRESHOLD")
    embedding_threshold: float = Field(0.65, validation_alias="EMBEDDING_THRESHOLD")
    embedding_min_margin: float = Field(0.03, validation_alias="EMBEDDING_MIN_MARGIN")
    emergent_threshold: float = Field(0.45, validation_alias="EMERGENT_THRESHOLD")
    normalized_match_score: float = Field(0.95, validation_alias="NORMALIZED_MATCH_SCORE")

    cache_dir: Path = Field(Path(".cache"), validation_alias="CACHE_DIR")
    taxonomy_path: Path = Field(
        Path(__file__).resolve().parents[1] / "taxonomy" / "taxonomy.json",
        validation_alias="TAXONOMY_PATH",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Instancia global de configuración. Se carga al importar el módulo.
settings = Settings()
