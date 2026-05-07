from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from sqlalchemy.orm import Session
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from dotenv import load_dotenv
from pathlib import Path
from pathlib import Path
import os
import asyncio
import uuid

# --- 1. CONFIGURACIÓN INICIAL: CARGAR VARIABLES DE ENTORNO ---
ROOT_DIR = Path(__file__).parent.parent
env_path = ROOT_DIR / '.env'
load_dotenv(dotenv_path=env_path)

# Configurar ruta absoluta para Firebase si existe la variable
relative_cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH')
if relative_cred_path:
    absolute_cred_path = str(ROOT_DIR / relative_cred_path)
    os.environ['FIREBASE_CREDENTIALS_PATH'] = absolute_cred_path
    print(f"Ruta de credenciales de Firebase establecida en: {absolute_cred_path}")

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
Base.metadata.create_all(bind=engine)

# --- 3. CONFIGURACIÓN DE LA APP ---
app = FastAPI(
    title="Sistema de Asignación Docente - API",
    description="API REST para el sistema inteligente de asignación docente",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:3000",
        "http://localhost:8080",
        "http://localhost:8000",
        "https://semilleros-493300.web.app",
        "https://semilleros-493300.firebaseapp.com",
    ],
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
        database_connected=db_ok
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
        print(f"Error listando archivos: {e}")
        raise HTTPException(status_code=500, detail=f"Error listando archivos: {str(e)}")

from fastapi import Request, BackgroundTasks
import time
import threading

drive_download_lock = threading.Lock()

folder_tokens = {}

def process_historical_queue(archivos: list, entidad_inferida: str, folder_id: str):
    """
    Procesa una lista de archivos secuencialmente con pausas para liberar RAM.
    """
    access_token = folder_tokens.get(folder_id)
    if not access_token:
        print(f"❌ Error: No se encontró access_token en memoria para el folder_id {folder_id}. Abortando.")
        return

    for archivo in archivos:
        process_drive_file_async(archivo['id'], archivo.get('name', 'desconocido'), entidad_inferida, access_token)
        time.sleep(3)  # Permite al Garbage Collector liberar memoria de pdfplumber


def process_drive_file_async(drive_file_id: str, file_name: str, entidad: str, access_token: str):
    """
    Procesador central en segundo plano. 
    Abre y gestiona su propia sesión de base de datos.
    """
    if file_name == 'webhook_event' or drive_file_id == 'test_id':
        print("Ignorando ping de prueba del webhook de Drive.")
        return
        
    db = SessionLocal()
    try:
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
                print(f"⚠️ Formato no soportado o entidad no inferible para {file_name}")
                return

        print(f"🔄 Descargando y procesando {entidad}: {file_name}")
        
        # 2. Descarga
        with drive_download_lock:
            file_bytes = drive_service.download_file_thread_safe(drive_file_id, access_token)
            
        if not file_bytes:
            raise Exception("No se pudo descargar el archivo.")

        # 3. Enrutamiento, Procesamiento IA y Persistencia
        if entidad == "docente":
            from backend.services.pdf_processor import PDFProcessor
            processor = PDFProcessor()
            data = processor.extract_cv_info(file_bytes, file_name)
            if data.get("success", False) or "name" in data:  # Dependiendo del output de extract_cv_info
                processor.save_docente_to_db(db, data, drive_file_id)
            else:
                raise Exception(data.get("error", "Error desconocido en CV"))

        elif entidad == "curso":
            from backend.services.docx_processor import DocxProcessor
            processor = DocxProcessor()
            data = processor.extract_syllabus_info(file_bytes, file_name)
            if data.get("success", False) or "nombre" in data:
                processor.save_curso_to_db(db, data, drive_file_id)
            else:
                raise Exception(data.get("error", "Error desconocido en Sílabo"))

        elif entidad == "horario":
            from backend.services.schedule_processor import ScheduleProcessor
            temp_path = f"/tmp/{drive_file_id}.pdf"
            with open(temp_path, "wb") as f:
                f.write(file_bytes)
            try:
                processor = ScheduleProcessor()
                data_list = processor.extract_schedule_data(temp_path)
                if data_list:
                    processor.save_history_to_db(db, data_list)
                else:
                    raise Exception("No se extrajeron datos válidos del horario.")
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        # 4. Confirmación Transaccional
        db.commit()
        print(f"✅ Procesamiento y guardado exitoso: {file_name}")

    except Exception as e:
        db.rollback()
        print(f"❌ Error procesando {file_name}: {e}")
    finally:
        db.close()

@app.post("/api/webhooks/config/{folder_id}")
async def config_webhook(folder_id: str, background_tasks: BackgroundTasks, google_token: Optional[str] = Header(None, alias="X-Drive-Token"), user: dict = Depends(get_current_user)):
    if not google_token:
        raise HTTPException(status_code=401, detail="Token de Google requerido")
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
            # Procesamiento Híbrido: Obtener archivos preexistentes (Paginación Completa)
            archivos = []
            page_token = None
            
            while True:
                archivos_data = drive_service.service.files().list(
                    q=f"'{folder_id}' in parents and trashed=false",
                    fields="nextPageToken, files(id, name)",
                    pageSize=1000,
                    pageToken=page_token
                ).execute()
                
                archivos.extend(archivos_data.get('files', []))
                page_token = archivos_data.get('nextPageToken')
                
                if not page_token:
                    break
            
            # Encolar la lista completa para ser procesada secuencialmente
            background_tasks.add_task(process_historical_queue, archivos, "desconocida", folder_id)
            
            return {"success": True, "message": f"Webhook activo. Procesando {len(archivos)} archivos preexistentes.", "channel_id": channel_id}
        else:
            raise HTTPException(status_code=500, detail="No se pudo registrar el webhook en Google Drive. Verifica permisos.")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error configurando webhook: {str(e)}")

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
    except:
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
            print(f"❌ Error: No se encontró access_token en memoria para el channel_id {channel_id}. Ignorando.")
            return {"status": "error", "message": "No access_token found"}

        # Tarea delegada a la misma función global asíncrona real
        background_tasks.add_task(
            process_drive_file_async,
            drive_file_id=drive_file_id,
            file_name="webhook_event",
            entidad=entidad,
            access_token=access_token
        )
        return {"status": "processing_started", "drive_file_id": drive_file_id}
        
    return {"status": "ignored"}

# --- 7. CONSULTAS A LA BD (PROTEGIDAS) ---
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
                "areas": d.areas, 
                "herramientas": d.herramientas, 
                "lenguajes": d.lenguajes,
                "metodologias": d.metodologias
            } for d in docentes
        ]
    }

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
                "areas": c.areas, 
                "lenguajes": c.lenguajes, 
                "herramientas": c.herramientas, 
                "metodologias": c.metodologias
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
        
        print(f"🎯 Generando recomendaciones de docentes para curso: {curso.nombre}")
        
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
        print(f"❌ Error generando recomendaciones de docentes: {e}")
        raise HTTPException(status_code=500, detail=f"Error generando recomendaciones: {str(e)}")

# --- 9. ENDPOINTS DE DEBUG ELIMINADOS ---
# Los endpoints /api/debug/ner-profile fueron removidos debido a la adopción del LLM Unificado (Gemini)
# que reemplaza la extracción basada en diccionarios NER.

# --- EJECUCIÓN LOCAL O CLOUD RUN ---
if __name__ == "__main__":
    import uvicorn
    # Cloud Run inyecta la variable de entorno PORT, por defecto usamos 8080 si no existe
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 Servidor iniciando en http://0.0.0.0:{port} ...")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port)