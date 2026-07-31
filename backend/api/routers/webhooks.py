"""Router de configuracion y recepcion de Webhooks."""
import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user, get_current_user_email
from backend.database.db_session import SessionLocal
from backend.database import crud
from backend.drive.drive_service import drive_service
from backend.core import state
from backend.core.task_manager import process_historical_queue, process_historical_queue_all
from backend.services.drive_token_service import upsert_tokens

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["webhooks"])


class ConfigAllRequest(BaseModel):
  cvs_folder_id: str
  syllabi_folder_id: str
  schedules_folder_id: str


class ExtractRequest(BaseModel):
  file_id: str
  file_name: str
  entidad: str
  access_token: str
  propietario_email: str = "legacy@upao.edu.pe"


def get_db_session_for_webhook():
  db = SessionLocal()
  try:
    yield db
  finally:
    db.close()


def _webhook_base_url() -> str:
  base = (os.environ.get("WEBHOOK_BASE_URL") or "").rstrip("/")
  if not base.startswith("http"):
    raise HTTPException(
      status_code=500,
      detail="WEBHOOK_BASE_URL no configurada en el servicio (debe ser la URL pública de Cloud Run).",
    )
  return base


def _persist_access_token(email: str, google_token: str) -> None:
  db = SessionLocal()
  try:
    upsert_tokens(db, email, google_token, expires_in=3500)
  except Exception as e:
    logger.warning("No se pudo persistir access_token Drive: %s", e)
  finally:
    db.close()


@router.post("/debug/extract")
def debug_extract(req: ExtractRequest, background_tasks: BackgroundTasks):
  # Nuevo formato de contexto: (nombre, email)
  state.memoria_tareas[req.file_id] = (req.file_name, req.propietario_email)
  db = SessionLocal()
  crud.create_webhook_log(
    db, req.file_id, "add", req.entidad, "received", propietario_email=req.propietario_email
  )
  if req.access_token:
    upsert_tokens(db, req.propietario_email, req.access_token, expires_in=3500)
  db.close()
  return {"message": "Encolado"}


@router.post("/webhooks/config/{folder_id}")
async def config_webhook(
  folder_id: str,
  background_tasks: BackgroundTasks,
  google_token: Optional[str] = Header(None, alias="X-Drive-Token"),
  user: dict = Depends(get_current_user),
  email: str = Depends(get_current_user_email),
):
  if not google_token:
    raise HTTPException(status_code=401, detail="Token de Google requerido")

  if folder_id in state.folder_tokens:
    return {"success": True, "message": "Carpeta ya configurada previamente"}

  state.folder_propietarios[folder_id] = email
  try:
    if not drive_service.build_service(google_token):
      raise HTTPException(status_code=500, detail="Error conectando con Drive")

    _persist_access_token(email, google_token)

    channel_id = str(uuid.uuid4())
    state.folder_tokens[folder_id] = email
    state.folder_tokens[channel_id] = email

    webhook_url = f"{_webhook_base_url()}/api/webhooks/drive"
    response = drive_service.register_webhook(folder_id, webhook_url, channel_id)
    if response:
      archivos = drive_service.list_files_in_folder(folder_id, file_types=None, recursive=True)
      background_tasks.add_task(process_historical_queue, archivos, "desconocida", folder_id, email)
      return {
        "success": True,
        "message": f"Webhook activo. Procesando {len(archivos)} archivos preexistentes.",
        "channel_id": channel_id,
      }
    raise HTTPException(status_code=500, detail="No se pudo registrar el webhook en Google Drive.")
  except HTTPException:
    raise
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Error configurando webhook: {str(e)}")


@router.post("/webhooks/config_all")
async def config_all_webhooks(
  request: ConfigAllRequest,
  background_tasks: BackgroundTasks,
  google_token: Optional[str] = Header(None, alias="X-Drive-Token"),
  user: dict = Depends(get_current_user),
  email: str = Depends(get_current_user_email),
  db: Session = Depends(get_db_session_for_webhook),
):
  if not google_token:
    raise HTTPException(status_code=401, detail="Token de Google requerido")

  try:
    if not drive_service.build_service(google_token):
      raise HTTPException(status_code=500, detail="Error conectando con Drive")

    _persist_access_token(email, google_token)

    webhook_url = f"{_webhook_base_url()}/api/webhooks/drive"

    def register_and_list(folder_id: str, entidad: str):
      # Siempre refresca propietario y token de canal
      state.folder_propietarios[folder_id] = email
      state.folder_tokens[folder_id] = email
      ch_id = str(uuid.uuid4())
      state.folder_tokens[ch_id] = email
      state.folder_propietarios[ch_id] = email
      state.canal_a_entidad[ch_id] = entidad
      drive_service.register_webhook(folder_id, webhook_url, ch_id)
      return drive_service.list_files_in_folder(folder_id, file_types=None, recursive=True)

    archivos_sched = register_and_list(request.schedules_folder_id, "horario")
    archivos_syl = register_and_list(request.syllabi_folder_id, "curso")
    archivos_cv = register_and_list(request.cvs_folder_id, "docente")

    background_tasks.add_task(
      process_historical_queue_all, archivos_sched, archivos_syl, archivos_cv, google_token, email
    )

    total = len(archivos_sched) + len(archivos_syl) + len(archivos_cv)
    return {"success": True, "message": f"Webhooks activos. {total} archivos encolados."}
  except HTTPException:
    raise
  except Exception as e:
    logger.error(f"Error en config_all: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhooks/drive")
async def drive_webhook(
  request: Request,
  background_tasks: BackgroundTasks,
  db: Session = Depends(get_db_session_for_webhook),
):
  channel_id = request.headers.get("X-Goog-Channel-ID")
  resource_state = request.headers.get("X-Goog-Resource-State")

  try:
    body = await request.json()
  except Exception:
    body = {}

  drive_file_id = body.get("drive_file_id", "test_id")
  evento_tipo = body.get("evento_tipo", resource_state or "update")

  entidad = state.canal_a_entidad.get(channel_id, body.get("entidad", "docente"))
  propietario_email = state.folder_propietarios.get(channel_id, "legacy@upao.edu.pe")
  crud.create_webhook_log(
    db, drive_file_id, evento_tipo, entidad, "received", propietario_email=propietario_email
  )

  if evento_tipo in ["trash", "delete"]:
    if entidad == "docente":
      docente = crud.get_docente_by_drive_id(db, drive_file_id)
      if docente:
        crud.delete_docente(db, docente.id)
    elif entidad == "curso":
      curso = crud.get_curso_by_drive_id(db, drive_file_id)
      if curso:
        db.delete(curso)
        db.commit()
    return {"status": "deleted", "drive_file_id": drive_file_id}

  if evento_tipo in ["add", "update"]:
    # Contexto nuevo: (nombre provisional, email) — el daemon resuelve token fresco
    owner = propietario_email
    state.memoria_tareas[drive_file_id] = ("webhook_event", owner)
    logger.info(f"Webhook event para {drive_file_id} encolado (owner={owner}).")
    return {"status": "enqueued", "drive_file_id": drive_file_id}

  return {"status": "ignored"}
