"""
Punto de entrada de la API REST de Teacher_Ideal.

La aplicación FastAPI se configura aquí e incluye los routers modularizados.
El procesamiento de archivos y webhooks se delegaron a sus respectivos módulos
para mantener una arquitectura limpia.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

# --- 1. CONFIGURACIÓN INICIAL: CARGAR VARIABLES DE ENTORNO ---
ROOT_DIR = Path(__file__).parent.parent
env_path = ROOT_DIR / ".env"
load_dotenv(dotenv_path=env_path)

relative_cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
if relative_cred_path:
  absolute_cred_path = str(ROOT_DIR / relative_cred_path)
  os.environ["FIREBASE_CREDENTIALS_PATH"] = absolute_cred_path
  logger.info(f"Ruta de credenciales de Firebase establecida en: {absolute_cred_path}")

# --- 2. IMPORTS DE SERVICIOS ---
from backend.database.db_session import init_db
from backend.core.task_manager import start_daemon

import backend.database.models # noqa: F401

init_db()

# --- 3. RUTERS MODULARIZADOS ---
from backend.api.routers import auth, cursos, docentes, drive, recommendations, system, webhooks, colaboradores

# --- 4. CONFIGURACIÓN DE LA APP ---
app = FastAPI(
  title="Sistema de Asignación Docente - API",
  description="API REST para el sistema inteligente de asignación docente",
  version="1.0.0",
)

_default_origins = [
  "https://semilleros-493300.web.app",
  "https://semilleros-493300.firebaseapp.com",
  "https://vektora.web.app",
  "https://vektora.firebaseapp.com",
]
_extra_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
  CORSMiddleware,
  allow_origins=_default_origins + _extra_origins,
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(cursos.router)
app.include_router(docentes.router)
app.include_router(drive.router)
app.include_router(recommendations.router)
app.include_router(system.router)
app.include_router(webhooks.router)
app.include_router(colaboradores.router)


# --- 5. RUTAS BÁSICAS ---
@app.get("/", include_in_schema=False)
def read_root():
  html_content = """
  <!DOCTYPE html>
  <html>
    <head>
      <meta name="google-site-verification" content="zUnBO9B8AnQROxDHRiu2ZNhwwi-KsPWz_mwY3IOcs7s" />
      <title>Backend API</title>
    </head>
    <body>
      <h1>API Backend Activo</h1>
    </body>
  </html>
  """
  return HTMLResponse(content=html_content)

@app.get("/health")
async def health_check():
  return {"status": "ok", "database": "connected"}

@app.on_event("startup")
def startup_event():
  start_daemon()

if __name__ == "__main__":
  import uvicorn
  port = int(os.environ.get("PORT", 8080))
  logger.info(f"Servidor iniciando en http://0.0.0.0:{port} ...")
  uvicorn.run("backend.main:app", host="0.0.0.0", port=port)
