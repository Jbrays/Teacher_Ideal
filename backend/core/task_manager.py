"""Gestor de tareas en segundo plano para procesar archivos de Drive."""
import logging
import os
import time
import threading
from backend.database.db_session import SessionLocal
from backend.database import crud
from backend.drive.drive_service import drive_service
from backend.services.curso_service import CursoService
from backend.services.docente_service import DocenteService
from backend.services.schedule_service import ScheduleService
from backend.services.taxonomy_service import TaxonomyService
from backend.services.drive_token_service import get_valid_access_token
from backend.core import state
from backend.database.models import WebhookLog, UserDriveToken


logger = logging.getLogger(__name__)

def process_historical_queue(archivos: list, entidad_inferida: str, folder_id: str, propietario_email: str = "legacy@upao.edu.pe"):
  """Encola archivos preexistentes. Contexto = (nombre, email dueño) para renovar token al descargar."""
  email = (propietario_email or "").strip().lower()
  if not email:
    logger.error(f"Sin propietario_email para folder_id {folder_id}. Abortando.")
    return

  db = SessionLocal()
  try:
    contexts = []
    for archivo in archivos:
      archivo_nombre = archivo.get("name", "desconocido")
      contexts.append((archivo["id"], archivo_nombre))
      db.add(WebhookLog(
        drive_file_id=archivo["id"],
        evento_tipo="add",
        entidad=entidad_inferida,
        status="received",
        propietario_email=email,
      ))
    db.commit()
    for file_id, archivo_nombre in contexts:
      state.memoria_tareas[file_id] = (archivo_nombre, email)
      logger.info(f"Archivo historico {archivo_nombre} encolado como {entidad_inferida}.")
    return len(contexts)
  except Exception:
    db.rollback()
    logger.exception("No se pudo guardar la cola historica de %s", entidad_inferida)
    raise
  finally:
    db.close()

def process_historical_queue_all(archivos_sched: list, archivos_syl: list, archivos_cv: list, access_token: str, propietario_email: str = "legacy@upao.edu.pe"):
  """Encola horarios, sílabos y CVs. El access_token se usa solo para seed; la descarga renueva desde DB."""
  from backend.services.drive_token_service import upsert_tokens

  email = (propietario_email or "").strip().lower()
  db = SessionLocal()
  try:
    if access_token and email:
      existing = db.query(UserDriveToken).filter(UserDriveToken.email == email).first()
      upsert_tokens(
        db,
        email,
        access_token,
        refresh_token=existing.refresh_token if existing else None,
        expires_in=3500,
        commit=False,
      )

    contexts = []
    def encolar(archivos, entidad_real):
      for archivo in archivos:
        archivo_nombre = archivo.get("name", "desconocido")
        contexts.append((archivo["id"], archivo_nombre, entidad_real))
        db.add(WebhookLog(
          drive_file_id=archivo["id"],
          evento_tipo="add",
          entidad=entidad_real,
          status="received",
          propietario_email=email,
        ))

    encolar(archivos_sched, "horario")
    encolar(archivos_syl, "curso")
    encolar(archivos_cv, "docente")
    db.commit()

    for file_id, archivo_nombre, entidad_real in contexts:
      state.memoria_tareas[file_id] = (archivo_nombre, email)
      logger.info(f"Archivo {archivo_nombre} encolado como {entidad_real}.")
    return len(contexts)
  except Exception:
    db.rollback()
    logger.exception("No se pudo guardar atomicamente la cola historica")
    raise
  finally:
    db.close()

def process_drive_file_async(log_id: int, drive_file_id: str, file_name: str, entidad: str, owner_email: str, propietario_email: str = "legacy@upao.edu.pe"):
  if file_name == "webhook_event" or drive_file_id == "test_id":
    logger.info("Ignorando ping de prueba del webhook de Drive.")
    db_temp = SessionLocal()
    try:
      crud.update_webhook_log_status_by_id(db_temp, log_id, "processed")
    finally:
      db_temp.close()
    return

  db = SessionLocal()
  try:
    crud.update_webhook_log_status_by_id(db, log_id, "processing")

    if entidad == "desconocida":
      logger.warning(f"Entidad no inferible (sin canal configurado) para {file_name}")
      crud.update_webhook_log_status_by_id(db, log_id, "error")
      return

    email = (owner_email or propietario_email or "").strip().lower()
    access_token = get_valid_access_token(db, email)
    if not access_token:
      raise Exception(
        f"No hay token de Drive válido para {email}. "
        "El usuario debe iniciar sesión de nuevo y autorizar Drive (offline)."
      )

    logger.info(f"Descargando y procesando {entidad}: {file_name} (user={email})")

    file_bytes = drive_service.download_file_thread_safe(drive_file_id, access_token)

    if not file_bytes:
      # Reintento con refresh forzado (access_token puede haber sido revocado/expirado)
      logger.warning("Descarga falló para %s; forzando refresh de token Drive de %s", file_name, email)
      access_token = get_valid_access_token(db, email, force_refresh=True)
      file_bytes = drive_service.download_file_thread_safe(drive_file_id, access_token) if access_token else None
    if not file_bytes:
      raise Exception(
        "No se pudo descargar el archivo (token Drive inválido o sin permisos). "
        "Cierra sesión, vuelve a entrar y acepta el permiso offline de Drive."
      )

    if entidad == "docente":
      docente_service = DocenteService(db)
      doc_id = docente_service.extract_and_save(file_bytes, drive_file_id, file_name, propietario_email=email)
      if not doc_id:
        raise Exception("Error procesando o guardando CV")
      TaxonomyService(db).process_docente(doc_id)
    elif entidad == "curso":
      curso_service = CursoService(db)
      curso_id = curso_service.extract_and_save(file_bytes, drive_file_id, file_name, propietario_email=email)
      if not curso_id:
        raise Exception("Error procesando o guardando Silabo")
      TaxonomyService(db).process_curso(curso_id)
    elif entidad == "horario":
      temp_path = f"/tmp/{drive_file_id}.pdf"
      with open(temp_path, "wb") as f:
        f.write(file_bytes)
      try:
        schedule_service = ScheduleService(db)
        success = schedule_service.extract_and_save(temp_path, file_name, propietario_email=email)
        if not success:
          raise Exception("No se extrajeron o guardaron datos validos del horario.")
      finally:
        if os.path.exists(temp_path):
          os.remove(temp_path)

    db.commit()
    logger.info(f"Procesamiento asincrono completado para {file_name}")
    crud.update_webhook_log_status_by_id(db, log_id, "processed")

  except Exception as e:
    db.rollback()
    logger.error(f"Error en process_drive_file_async ({file_name}): {e}")
    crud.update_webhook_log_status_by_id(db, log_id, "error")
  finally:
    db.close()

def daemon_despachador():
  db = SessionLocal()
  while True:
    try:
      db.commit()
      from backend.database.models import WebhookLog
      pendientes = db.query(WebhookLog).filter(
        WebhookLog.status == "received"
      ).order_by(WebhookLog.timestamp.asc()).all()

      if not pendientes:
        continue

      horarios_activos = db.query(WebhookLog).filter(
        WebhookLog.entidad == "horario",
        WebhookLog.status.in_(["received", "processing"]),
      ).count()

      for webhook in pendientes:
        contexto = state.memoria_tareas.get(webhook.drive_file_id)
        # Contexto: (file_name, owner_email) — compatible con legado (file_name, access_token)
        if not contexto:
          # Fallback: usar propietario del log y nombre genérico
          owner = (webhook.propietario_email or "").strip().lower()
          if not owner:
            logger.error(f"Webhook huerfano. Marcando {webhook.drive_file_id} como failed.")
            webhook.status = "failed"
            db.commit()
            continue
          file_name = webhook.drive_file_id
          owner_email = owner
        else:
          file_name, owner_or_token = contexto
          # Si parece email, es el nuevo formato; si no, es access_token legado
          if "@" in str(owner_or_token):
            owner_email = str(owner_or_token).strip().lower()
          else:
            owner_email = (webhook.propietario_email or "").strip().lower()
            # Actualiza token legado en DB si es posible
            if owner_email and owner_or_token:
              try:
                from backend.services.drive_token_service import upsert_tokens
                upsert_tokens(db, owner_email, owner_or_token, expires_in=1800)
              except Exception:
                pass

        if webhook.entidad == "docente" and horarios_activos > 0:
          continue

        logger.info(f"Despachando {webhook.entidad} {file_name} al ThreadPool...")
        webhook.status = "processing"
        db.commit()
        prop_email = (webhook.propietario_email or owner_email or "legacy@upao.edu.pe").strip().lower()
        state.background_executor.submit(
          process_drive_file_async,
          webhook.id,
          webhook.drive_file_id,
          file_name,
          webhook.entidad,
          owner_email or prop_email,
          propietario_email=prop_email,
        )

    except Exception as e:
      logger.error(f"Error en daemon_despachador: {e}", exc_info=True)
    finally:
      time.sleep(15)

def start_daemon():
  logger.info("Iniciando Daemon Despachador de Tareas...")
  hilo_daemon = threading.Thread(target=daemon_despachador, daemon=True)
  hilo_daemon.start()
