from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from pathlib import Path
import os
import sys
import asyncio
import uuid
import logging
import concurrent.futures
import threading
import csv
import io
from fpdf import FPDF

memoria_tareas = {}
background_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

logger = logging.getLogger(__name__)

# --- 1. CONFIGURACIÓN INICIAL: CARGAR VARIABLES DE ENTORNO ---
ROOT_DIR = Path(__file__).parent.parent
env_path = ROOT_DIR / '.env'
load_dotenv(dotenv_path=env_path)

# Configurar ruta absoluta para Firebase si existe la variable
relative_cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH')
if relative_cred_path:
    absolute_cred_path = str(ROOT_DIR / relative_cred_path)
    os.environ['FIREBASE_CREDENTIALS_PATH'] = absolute_cred_path
    logger.info(f"Ruta de credenciales de Firebase establecida en: {absolute_cred_path}")

# --- 2. IMPORTS DE SERVICIOS ---
from backend.auth.firebase import firebase_auth
from backend.drive.drive_service import drive_service
from backend.services.pdf_processor import pdf_processor
from backend.services.docx_processor import docx_processor
from backend.services.schedule_processor import schedule_processor 
from backend.services.recommendation_engine import recommendation_engine
from backend.services.embeddings_manager import embeddings_manager
from backend.models.schemas import UserLogin, UserResponse, AuthResponse, SystemStatus
from backend.database.db_session import get_db, init_db
from backend.database import crud
from backend.database.models import Docente, Curso

# Inicializar la base de datos
from backend.database.db_session import engine, Base, SessionLocal
import backend.database.models  # Importar explícitamente para asegurar que los modelos están registrados

init_db()

# --- 3. CONFIGURACIÓN DE LA APP ---
app = FastAPI(
    title="Sistema de Asignación Docente - API",
    description="API REST para el sistema inteligente de asignación docente",
    version="1.0.0"
)

_default_origins = [
    "https://semilleros-493300.web.app",
    "https://semilleros-493300.firebaseapp.com",
    "https://vektora.web.app",
    "https://vektora.firebaseapp.com",
]
_extra_origins = [
    o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_origins + _extra_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 4. RUTAS BÁSICAS Y AUTENTICACIÓN ---
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

@app.get("/api/status", response_model=SystemStatus)
async def api_status(db: Session = Depends(get_db)):
    db_ok = False
    try:
        db.query(Docente).first()
        db_ok = True
    except Exception:
        db_ok = False
    return SystemStatus(
        status="running",
        version="1.0.0",
        features=["Firebase Auth", "Drive Integration", "NER Processing", "SBERT Recommendations", "Schedule Analysis"],
        firebase_connected=firebase_auth.app is not None,
        drive_connected=drive_service.service is not None,
        database_connected=db_ok,
        python_version=sys.version
    )

@app.post("/api/auth/verify", response_model=AuthResponse)
async def verify_token(login_data: UserLogin):
    try:
        user_info = firebase_auth.verify_token(login_data.token)
        if user_info:
            user_response = UserResponse(
                uid=user_info['uid'],
                email=user_info['email'],
                name=user_info.get('name'),
                picture=user_info.get('picture'),
                email_verified=user_info.get('email_verified', False)
            )
            return AuthResponse(success=True, user=user_response, message="Token verificado")
        return AuthResponse(success=False, message="Token inválido o expirado")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error verificando token: {str(e)}")

@app.get("/api/auth/user/{uid}", response_model=UserResponse)
async def get_user_info(uid: str):
    try:
        user_info = firebase_auth.get_user(uid)
        if not user_info:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return UserResponse(
            uid=user_info['uid'],
            email=user_info['email'],
            name=user_info.get('name'),
            picture=user_info.get('picture'),
            email_verified=user_info.get('email_verified', False)
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error obteniendo usuario: {str(e)}")

async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Token de autorización requerido")
    try:
        token = authorization.replace("Bearer ", "")
        user_info = firebase_auth.verify_token(token)
        if not user_info:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")
        return user_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Error interno de autenticación: {str(e)}")


async def require_admin(user: dict = Depends(get_current_user)):
    """Verifica que el usuario autenticado sea administrador."""
    admin_emails = os.getenv("ADMIN_EMAILS", "").split(",")
    admin_emails = [email.strip().lower() for email in admin_emails if email.strip()]
    user_email = user.get("email", "").lower()

    if not admin_emails:
        logger.warning("ADMIN_EMAILS no está configurado. Acceso admin denegado por seguridad.")
        raise HTTPException(status_code=403, detail="Acceso denegado: no hay administradores configurados")

    if user_email not in admin_emails:
        logger.warning(f"Usuario {user_email} intentó acceder a un endpoint administrativo.")
        raise HTTPException(status_code=403, detail="Acceso denegado: se requieren permisos de administrador")

    return user


# --- 5. GOOGLE DRIVE ---
@app.get("/api/drive/folders")
async def list_drive_folders(parent_id: Optional[str] = None, authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Token requerido")
    try:
        access_token = authorization.replace("Bearer ", "")
        if not drive_service.build_service(access_token):
            raise HTTPException(status_code=500, detail="Error conectando con Drive")
        folders = drive_service.list_folders(parent_id=parent_id)
        return {"success": True, "count": len(folders), "folders": folders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listando carpetas: {str(e)}")

@app.get("/api/drive/folders/{folder_id}/files")
async def list_folder_files(folder_id: str, authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Token de autorización requerido")
    try:
        access_token = authorization.replace("Bearer ", "")
        if not drive_service.build_service(access_token):
            raise HTTPException(status_code=500, detail="Error conectando con Drive")
        file_types = [
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        ]
        files = drive_service.list_files_in_folder(folder_id, file_types)
        pdf_count = sum(1 for f in files if f['mimeType'] == 'application/pdf')
        docx_count = sum(1 for f in files if 'wordprocessingml' in f['mimeType'])
        
        return {
            "success": True,
            "folder_id": folder_id,
            "total_files": len(files),
            "pdf_files": pdf_count,
            "docx_files": docx_count,
            "files": files
        }
    except Exception as e:
        logger.error(f"Error listando archivos: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error listando archivos: {str(e)}")

from fastapi import Request, BackgroundTasks
import time
import threading

drive_download_lock = threading.Lock()

folder_tokens = {}

def process_historical_queue(archivos: list, entidad_inferida: str, folder_id: str):
    """
    Encola una lista de archivos en la base de datos para el daemon despachador.
    """
    access_token = folder_tokens.get(folder_id)
    if not access_token:
        logger.error(f"❌ Error: No se encontró access_token en memoria para el folder_id {folder_id}. Abortando.")
        return

    db = SessionLocal()
    try:
        for archivo in archivos:
            archivo_nombre = archivo.get('name', 'desconocido')
            name_lower = archivo_nombre.lower()
            
            entidad_real = entidad_inferida
            if entidad_real == "desconocida":
                if name_lower.endswith(".docx"):
                    entidad_real = "curso"
                elif name_lower.endswith(".pdf") and "horario" in name_lower:
                    entidad_real = "horario"
                elif name_lower.endswith(".pdf"):
                    entidad_real = "docente"
                    
            # Registrar en memoria para que el daemon lo encuentre
            memoria_tareas[archivo['id']] = (archivo_nombre, access_token)
            # Insertar en BD para encolamiento persistente
            crud.create_webhook_log(db, archivo['id'], "add", entidad_real, "received")
            logger.info(f"📥 Archivo histórico {archivo_nombre} encolado exitosamente como {entidad_real}.")
    finally:
        db.close()

from pydantic import BaseModel

class ConfigAllRequest(BaseModel):
    cvs_folder_id: str
    syllabi_folder_id: str
    schedules_folder_id: str

def process_historical_queue_all(archivos_sched: list, archivos_syl: list, archivos_cv: list, access_token: str):
    db = SessionLocal()
    try:
        from backend.database import crud
        def encolar(archivos):
            for archivo in archivos:
                archivo_nombre = archivo.get('name', 'desconocido')
                name_lower = archivo_nombre.lower()
                entidad_real = "desconocida"
                if name_lower.endswith(".docx"):
                    entidad_real = "curso"
                elif name_lower.endswith(".pdf") and "horario" in name_lower:
                    entidad_real = "horario"
                elif name_lower.endswith(".pdf"):
                    entidad_real = "docente"
                memoria_tareas[archivo['id']] = (archivo_nombre, access_token)
                crud.create_webhook_log(db, archivo['id'], "add", entidad_real, "received")
                logger.info(f"📥 Archivo {archivo_nombre} encolado como {entidad_real}.")
        
        # Encolar en orden: horarios primero, luego sílabos, finalmente CVs
        encolar(archivos_sched)
        encolar(archivos_syl)
        encolar(archivos_cv)
    finally:
        db.close()


class ExtractRequest(BaseModel):
    file_id: str
    file_name: str
    entidad: str
    access_token: str

@app.post("/api/debug/extract")
def debug_extract(req: ExtractRequest, background_tasks: BackgroundTasks):
    memoria_tareas[req.file_id] = (req.file_name, req.access_token)
    db = SessionLocal()
    crud.create_webhook_log(db, req.file_id, "add", req.entidad, "received")
    db.close()
    return {"message": "Encolado"}

def daemon_despachador():
    db = SessionLocal()
    while True:
        try:
            db.commit() # Romper caché
            from backend.database.models import WebhookLog
            pendientes = db.query(WebhookLog).filter(
                WebhookLog.status == "received"
            ).order_by(WebhookLog.timestamp.asc()).all()

            if not pendientes:
                continue

            horarios_activos = db.query(WebhookLog).filter(
                WebhookLog.entidad == "horario",
                WebhookLog.status.in_(["received", "processing"])
            ).count()

            for webhook in pendientes:
                contexto = memoria_tareas.get(webhook.drive_file_id)
                if not contexto:
                    logger.error(f"❌ Webhook huérfano (reinicio contenedor). Marcando {webhook.drive_file_id} como failed.")
                    webhook.status = "failed"
                    db.commit()
                    continue
                
                file_name, access_token = contexto

                if webhook.entidad == "docente":
                    if horarios_activos > 0:
                        # Retraso aceptable de 15s si un horario termina justo ahora
                        continue
                
                logger.info(f"🚀 Despachando {webhook.entidad} {file_name} al ThreadPool...")
                webhook.status = "processing"
                db.commit()
                background_executor.submit(
                    process_drive_file_async,
                    webhook.drive_file_id,
                    file_name,
                    webhook.entidad,
                    access_token
                )
                
        except Exception as e:
            logger.error(f"Error en daemon_despachador: {e}", exc_info=True)
        finally:
            import time
            time.sleep(15)

@app.on_event("startup")
def startup_event():
    logger.info("🚀 Iniciando Daemon Despachador de Tareas...")
    hilo_daemon = threading.Thread(target=daemon_despachador, daemon=True)
    hilo_daemon.start()

def process_drive_file_async(drive_file_id: str, file_name: str, entidad: str, access_token: str):
    """
    Procesador central en segundo plano. 
    Abre y gestiona su propia sesión de base de datos.
    """
    if file_name == 'webhook_event' or drive_file_id == 'test_id':
        logger.info("Ignorando ping de prueba del webhook de Drive.")
        db_temp = SessionLocal()
        try:
            crud.update_webhook_log_status(db_temp, drive_file_id, "processed")
        finally:
            db_temp.close()
        return
        
    db = SessionLocal()
    try:
        # PRIMERA línea del hilo de fondo, antes de todo
        crud.update_webhook_log_status(db, drive_file_id, "processing")
        
        # 1. Inferencia de Entidad
        name_lower = file_name.lower()
        if entidad == "desconocida":
            if name_lower.endswith(".docx"):
                entidad = "curso"
            elif name_lower.endswith(".pdf") and "horario" in name_lower:
                entidad = "horario"
            elif name_lower.endswith(".pdf"):
                entidad = "docente"
            else:
                logger.warning(f"⚠️ Formato no soportado o entidad no inferible para {file_name}")
                crud.update_webhook_log_status(db, drive_file_id, "error")
                return

        logger.info(f"🔄 Descargando y procesando {entidad}: {file_name}")
        
        # 2. Descarga
        with drive_download_lock:
            file_bytes = drive_service.download_file_thread_safe(drive_file_id, access_token)
            
        if not file_bytes:
            raise Exception("No se pudo descargar el archivo.")

        # 3. Enrutamiento, Procesamiento IA y Persistencia
        if entidad == "docente":
            data = pdf_processor.extract_cv_info(file_bytes, file_name)
            if data.get("success", False) or "name" in data:
                pdf_processor.save_docente_to_db(db, data, drive_file_id)
            else:
                raise Exception(data.get("error", "Error desconocido en CV"))

        elif entidad == "curso":
            data = docx_processor.extract_syllabus_info(file_bytes, file_name)
            if data.get("success", False) or "nombre" in data:
                docx_processor.save_curso_to_db(db, data, drive_file_id)
            else:
                raise Exception(data.get("error", "Error desconocido en Sílabo"))

        elif entidad == "horario":
            temp_path = f"/tmp/{drive_file_id}.pdf"
            with open(temp_path, "wb") as f:
                f.write(file_bytes)
            try:
                data_list = schedule_processor.extract_schedule_data(temp_path)
                if data_list:
                    schedule_processor.save_history_to_db(db, data_list)
                else:
                    raise Exception("No se extrajeron datos válidos del horario.")
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        # 4. Confirmación Transaccional
        db.commit()
        logger.info(f"✅ Procesamiento asíncrono completado para {file_name}")
        crud.update_webhook_log_status(db, drive_file_id, "processed")
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error en process_drive_file_async ({file_name}): {e}")
        crud.update_webhook_log_status(db, drive_file_id, "error")
    finally:
        db.close()

@app.post("/api/webhooks/config/{folder_id}")
async def config_webhook(folder_id: str, background_tasks: BackgroundTasks, google_token: Optional[str] = Header(None, alias="X-Drive-Token"), user: dict = Depends(get_current_user)):
    if not google_token:
        raise HTTPException(status_code=401, detail="Token de Google requerido")
    
    if folder_id in folder_tokens:
        return {"success": True, "message": "Carpeta ya configurada previamente"}
        
    try:
        if not drive_service.build_service(google_token):
            raise HTTPException(status_code=500, detail="Error conectando con Drive")
        
        channel_id = str(uuid.uuid4())
        
        # Guardar token en memoria
        folder_tokens[folder_id] = google_token
        folder_tokens[channel_id] = google_token
        
        # URL base de producción, podría ser una variable de entorno en el futuro
        base_url = os.environ.get("WEBHOOK_BASE_URL", "https://teacher-ideal-121734839794.us-central1.run.app")
        webhook_url = f"{base_url}/api/webhooks/drive"
        
        response = drive_service.register_webhook(folder_id, webhook_url, channel_id)
        if response:
            # Procesamiento Híbrido: Obtener archivos preexistentes (recursivo, Shared Drives)
            archivos = drive_service.list_files_in_folder(folder_id, file_types=None, recursive=True)
            
            # Encolar la lista completa para ser procesada secuencialmente
            background_tasks.add_task(process_historical_queue, archivos, "desconocida", folder_id)
            
            return {"success": True, "message": f"Webhook activo. Procesando {len(archivos)} archivos preexistentes.", "channel_id": channel_id}
        else:
            raise HTTPException(status_code=500, detail="No se pudo registrar el webhook en Google Drive. Verifica permisos.")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error configurando webhook: {str(e)}")

@app.post("/api/webhooks/config_all")
async def config_all_webhooks(request: ConfigAllRequest, background_tasks: BackgroundTasks, google_token: Optional[str] = Header(None, alias="X-Drive-Token"), user: dict = Depends(get_current_user)):
    if not google_token:
        raise HTTPException(status_code=401, detail="Token de Google requerido")
    
    try:
        if not drive_service.build_service(google_token):
            raise HTTPException(status_code=500, detail="Error conectando con Drive")
        
        base_url = os.environ.get("WEBHOOK_BASE_URL", "https://teacher-ideal-121734839794.us-central1.run.app")
        webhook_url = f"{base_url}/api/webhooks/drive"
        
        def register_and_list(folder_id):
            if folder_id in folder_tokens:
                # Ya registrado, solo obtener archivos
                return drive_service.list_files_in_folder(folder_id, file_types=None, recursive=True)
                
            folder_tokens[folder_id] = google_token
            ch_id = str(uuid.uuid4())
            folder_tokens[ch_id] = google_token
            drive_service.register_webhook(folder_id, webhook_url, ch_id)
            return drive_service.list_files_in_folder(folder_id, file_types=None, recursive=True)
            
        archivos_sched = register_and_list(request.schedules_folder_id)
        archivos_syl = register_and_list(request.syllabi_folder_id)
        archivos_cv = register_and_list(request.cvs_folder_id)
        
        background_tasks.add_task(process_historical_queue_all, archivos_sched, archivos_syl, archivos_cv, google_token)
        
        total = len(archivos_sched) + len(archivos_syl) + len(archivos_cv)
        return {"success": True, "message": f"Webhooks activos. {total} archivos encolados sincrónicamente."}
        
    except Exception as e:
        logger.error(f"❌ Error en config_all: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- 6. WEBHOOKS DE DRIVE (PROCESAMIENTO AUTÓNOMO) ---

@app.post("/api/webhooks/drive")
async def drive_webhook(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Endpoint público para recibir notificaciones push de Google Drive.
    Gestiona creaciones, modificaciones y eliminaciones de forma asíncrona.
    """
    # Google Drive envía información vital en los headers
    channel_id = request.headers.get("X-Goog-Channel-ID")
    resource_id = request.headers.get("X-Goog-Resource-ID")
    resource_state = request.headers.get("X-Goog-Resource-State") # sync, add, update, trash, delete
    
    # Podríamos necesitar parsear el body si configuramos un webhook con payload
    # body = await request.json() si viene como json
    
    # Por ahora, simulamos que recibimos el drive_file_id y la entidad del body
    # (En la implementación real de Drive API, se tendría que consultar la API para ver qué cambió)
    try:
        body = await request.json()
    except Exception:
        body = {}

    drive_file_id = body.get("drive_file_id", "test_id")
    evento_tipo = body.get("evento_tipo", resource_state or "update")
    entidad = body.get("entidad", "docente") # docente, curso, horario
    
    # 1. Registrar el evento en logs
    crud.create_webhook_log(db, drive_file_id, evento_tipo, entidad, "received")

    if evento_tipo in ["trash", "delete"]:
        # Caché Quirúrgica: Eliminación instantánea (y en cascada)
        if entidad == "docente":
            docente = crud.get_docente_by_drive_id(db, drive_file_id)
            if docente:
                embeddings_manager.delete_docente_embedding(docente.id)
                crud.delete_docente(db, docente.id) # Esto borra historial y caché en cascada
        elif entidad == "curso":
            curso = crud.get_curso_by_drive_id(db, drive_file_id)
            if curso:
                # Aquí podrías tener delete_curso
                db.delete(curso)
                db.commit()
        return {"status": "deleted", "drive_file_id": drive_file_id}
        
    elif evento_tipo in ["add", "update"]:
        access_token = folder_tokens.get(channel_id)
        if not access_token:
            logger.error(f"❌ Error: No se encontró access_token en memoria para el channel_id {channel_id}. Ignorando.")
            return {"status": "error", "message": "No access_token found"}

        # Encolar en memoria para el daemon
        memoria_tareas[drive_file_id] = ("webhook_event", access_token)
        # Nota: El crud.create_webhook_log más arriba ya lo dejó en 'received'.
        logger.info(f"📥 Webhook event para {drive_file_id} encolado en BD y memoria_tareas.")
        return {"status": "enqueued", "drive_file_id": drive_file_id}
        
    return {"status": "ignored"}

# --- 7. ESTADO DEL SISTEMA ---
@app.get("/api/system/status")
async def get_system_status(db: Session = Depends(get_db)):
    count = crud.get_active_processing_count(db)
    return {"is_processing": count > 0, "pending_count": count}

# --- 8. CONSULTAS A LA BD (PROTEGIDAS) ---
@app.get("/api/docentes")
async def get_docentes(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    docentes = crud.get_all_docentes(db, skip=skip, limit=limit)
    return {
        "success": True, 
        "total": len(docentes), 
        "docentes": [
            {
                "id": d.id, 
                "nombre": d.nombre, 
                "email": d.email, 
                "grado": d.grado, 
                "entidades_clave": d.entidades_clave
            } for d in docentes
        ]
    }

@app.delete("/api/docentes/{docente_id}")
async def delete_docente_endpoint(docente_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    try:
        docente = crud.get_docente_by_id(db, docente_id)
        if not docente:
            raise HTTPException(status_code=404, detail=f"Docente con ID {docente_id} no encontrado")
        
        # 1. Purgar huella semántica (Derecho al olvido)
        embeddings_manager.delete_docente_embedding(docente.id)
        
        # 2. Eliminar de Base de Datos
        success = crud.delete_docente(db, docente.id)
        if not success:
            raise HTTPException(status_code=500, detail="Error eliminando docente de la base de datos")
            
        logger.info(f"🗑️ Docente {docente.nombre} (ID: {docente.id}) eliminado exitosamente (Perfil y Vectores).")
        return {"success": True, "message": "Docente eliminado correctamente"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error en endpoint delete_docente: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

@app.delete("/api/admin/clear_db")
async def clear_database(
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin)
):
    """Elimina permanentemente todos los registros y la base vectorial. Requiere rol admin."""
    try:
        from backend.database.models import RecomendacionCache, Recomendacion, Historial, Curso, Docente, WebhookLog
        # 1. Purgar base relacional en orden (evitar conflictos FK)
        db.query(RecomendacionCache).delete()
        db.query(Recomendacion).delete()
        db.query(Historial).delete()
        db.query(Curso).delete()
        db.query(Docente).delete()
        db.query(WebhookLog).delete()
        db.commit()

        # 2. Purgar ChromaDB
        embeddings_manager.clear_cache(item_type="all")
        
        logger.warning("🚨 Base de datos y ChromaDB han sido purgadas completamente mediante la zona de peligro.")
        return {"success": True, "message": "Base de datos y base vectorial borradas correctamente."}
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error purgiendo base de datos: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

@app.get("/api/ciclos")
async def get_ciclos(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    ciclos = crud.get_all_ciclos(db)
    return {"success": True, "ciclos": ciclos}

@app.get("/api/cursos")
async def get_cursos(ciclo: Optional[int] = None, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    cursos = crud.get_cursos_by_ciclo(db, ciclo) if ciclo else crud.get_all_cursos(db)
    return {
        "success": True, 
        "total": len(cursos), 
        "cursos": [
            {
                "id": c.id, 
                "nombre": c.nombre, 
                "codigo": c.codigo, 
                "ciclo": c.ciclo, 
                "temas": c.temas
            } for c in cursos
        ]
    }

# --- 8. RECOMENDACIONES ---
@app.get("/api/recommend/docentes/{curso_id}")
async def recommend_docentes(curso_id: int, top_k: int = 100, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        curso = crud.get_curso_by_id(db, curso_id)
        if not curso:
            raise HTTPException(status_code=404, detail=f"Curso con ID {curso_id} no encontrado")
        
        logger.info(f"🎯 Generando recomendaciones de docentes para curso: {curso.nombre}")
        
        # Llamada al motor de recomendación (SBERT + Historial)
        recommendations = recommendation_engine.recommend_docentes_for_curso(db=db, curso_id=curso_id, top_k=top_k)
        
        return {
            "success": True,
            "curso_id": curso_id,
            "curso_nombre": curso.nombre,
            "total_recommendations": len(recommendations),
            "recommendations": recommendations
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"❌ Error generando recomendaciones de docentes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generando recomendaciones: {str(e)}")

@app.get("/api/admin/export_recommendations")
async def export_all_recommendations(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        logger.info("⏳ Iniciando exportación masiva de recomendaciones...")
        cursos = crud.get_all_cursos(db, skip=0, limit=1000)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Curso ID", "Curso Nombre", "Ciclo", "Docente ID", "Docente Nombre", "Email", "Grado", "Score Combinado (%)", "Score Semantico (%)", "Score Tactico (%)", "Score Relativo (%)", "Confianza", "Explicacion IA"])

        for curso in cursos:
            logger.info(f"🔄 Generando/obteniendo recomendaciones para curso: {curso.nombre}")
            recommendations = recommendation_engine.recommend_docentes_for_curso(db=db, curso_id=curso.id, top_k=20)
            
            if not recommendations:
                writer.writerow([curso.id, curso.nombre, curso.ciclo or "N/A", "N/A", "Sin docentes recomendados", "", "", "0", "0", "0", "0", "", ""])
                continue
                
            for rec in recommendations:
                writer.writerow([
                    curso.id,
                    curso.nombre,
                    curso.ciclo or "N/A",
                    rec.get("docente_id", ""),
                    rec.get("nombre", ""),
                    rec.get("email", ""),
                    rec.get("grado", ""),
                    rec.get("score_combinado", 0),
                    rec.get("score_semantico", 0),
                    rec.get("score_historico", 0),
                    rec.get("score_relativo", 0),
                    rec.get("confianza_etiqueta", ""),
                    rec.get("xai_explanations", "").replace("\n", " ")
                ])
                
        output.seek(0)
        logger.info("✅ Exportación completa, enviando CSV.")
        return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=recomendaciones_completas.csv"})
        
    except Exception as e:
        logger.error(f"❌ Error exportando recomendaciones: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error exportando: {str(e)}")

@app.get("/api/recommend/docentes/{curso_id}/export_pdf")
async def export_curso_recommendations_pdf(curso_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        curso = crud.get_curso_by_id(db, curso_id)
        if not curso:
            raise HTTPException(status_code=404, detail=f"Curso con ID {curso_id} no encontrado")
        
        recommendations = recommendation_engine.recommend_docentes_for_curso(db=db, curso_id=curso_id, top_k=20)
        
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()
        
        pdf.set_fill_color(24, 24, 27)
        pdf.rect(0, 0, 210, 45, 'F')
        pdf.set_text_color(255, 255, 255)
        pdf.set_font('Helvetica', 'B', 20)
        pdf.set_y(10)
        pdf.cell(0, 10, 'RANKING DE DOCENTES', align='C', new_x='LMARGIN', new_y='NEXT')
        pdf.set_font('Helvetica', '', 12)
        pdf.cell(0, 8, curso.nombre.upper(), align='C', new_x='LMARGIN', new_y='NEXT')
        pdf.set_font('Helvetica', '', 9)
        pdf.cell(0, 6, f'Ciclo {curso.ciclo or "N/A"} | Generado por Vektora', align='C', new_x='LMARGIN', new_y='NEXT')
        
        pdf.set_y(50)
        pdf.set_text_color(0, 0, 0)
        
        if not recommendations:
            pdf.set_font('Helvetica', 'I', 12)
            pdf.cell(0, 10, 'No hay recomendaciones disponibles para este curso.', align='C')
        else:
            for idx, rec in enumerate(recommendations):
                if pdf.get_y() > 230:
                    pdf.add_page()
                    pdf.set_y(15)
                
                y_start = pdf.get_y()
                card_x = 10
                card_w = 190
                
                pdf.set_font('Helvetica', 'B', 24)
                pdf.set_text_color(180, 180, 180)
                pdf.set_xy(card_x + 2, y_start + 2)
                pdf.cell(15, 12, str(idx + 1), align='C')
                
                pdf.set_font('Helvetica', 'B', 13)
                pdf.set_text_color(24, 24, 27)
                pdf.set_xy(card_x + 20, y_start + 2)
                nombre_display = rec.get('nombre', '').title() if rec.get('nombre') else 'Sin nombre'
                pdf.cell(120, 7, nombre_display, align='L')
                
                pdf.set_font('Helvetica', '', 8)
                pdf.set_text_color(120, 120, 120)
                pdf.set_xy(card_x + 20, y_start + 9)
                pdf.cell(120, 5, rec.get('email', ''), align='L')
                
                score = rec.get('score_combinado', 0)
                pdf.set_font('Helvetica', 'B', 14)
                if idx == 0:
                    pdf.set_fill_color(234, 239, 255)
                    pdf.set_text_color(67, 56, 202)
                else:
                    pdf.set_fill_color(243, 244, 246)
                    pdf.set_text_color(24, 24, 27)
                pdf.set_xy(card_x + 155, y_start + 2)
                pdf.cell(30, 10, f'{score:.0f}%', align='C', fill=True)
                
                conf = rec.get('confianza_etiqueta', '')
                pdf.set_font('Helvetica', '', 8)
                if 'Muy Alta' in conf:
                    pdf.set_text_color(21, 128, 61)
                elif 'Alta' in conf:
                    pdf.set_text_color(29, 78, 216)
                elif 'Media' in conf:
                    pdf.set_text_color(161, 98, 7)
                else:
                    pdf.set_text_color(220, 38, 38)
                pdf.set_xy(card_x + 20, y_start + 16)
                pdf.cell(60, 5, conf, align='L')
                
                pdf.set_text_color(100, 100, 100)
                pdf.set_font('Helvetica', '', 7)
                pdf.set_xy(card_x + 80, y_start + 16)
                sem = rec.get('score_semantico', rec.get('score_est', 0))
                tac = rec.get('score_historico', rec.get('score_tac', 0))
                pdf.cell(80, 5, f'Sem: {sem:.0f}% | Tac: {tac:.0f}% | Rel: {rec.get("score_relativo", 0):.0f}%', align='L')
                
                xai = rec.get('xai_explanations', '')
                if xai:
                    pdf.set_font('Helvetica', '', 8)
                    pdf.set_text_color(55, 65, 81)
                    pdf.set_xy(card_x + 20, y_start + 23)
                    pdf.multi_cell(165, 4, xai, align='L')
                
                current_y = pdf.get_y() + 3
                pdf.set_draw_color(229, 231, 235)
                pdf.line(card_x + 5, current_y, card_x + card_w - 5, current_y)
                pdf.set_y(current_y + 5)
        
        pdf_bytes = pdf.output()
        output_buffer = io.BytesIO(pdf_bytes)
        output_buffer.seek(0)
        
        filename = f'ranking_{curso.nombre.replace(" ", "_")[:30]}.pdf'
        return StreamingResponse(
            output_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exportando PDF: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error exportando PDF: {str(e)}")

# --- 9. ENDPOINTS DE DEBUG ELIMINADOS ---
# Los endpoints /api/debug/ner-profile fueron removidos debido a la adopción del LLM Unificado (Gemini)
# que reemplaza la extracción basada en diccionarios NER.

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Servidor iniciando en http://0.0.0.0:{port} ...")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port)