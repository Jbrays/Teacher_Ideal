from fastapi import FastAPI, HTTPException, Depends, Header
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
from backend.services.ner_service import extract_entities
from backend.models.schemas import UserLogin, UserResponse, AuthResponse, SystemStatus
from backend.database.db_session import get_db, init_db
from backend.database import crud
from backend.database.models import Docente, Curso

# Inicializar la base de datos
init_db()

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
@app.get("/")
async def read_root():
    return {"message": "Sistema de Asignación Docente - API REST", "version": "1.0.0", "status": "active"}

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

# --- 6. PROCESAMIENTO DE ARCHIVOS ---

# A. PROCESAR CVs
@app.post("/api/drive/process-cvs/{folder_id}")
async def process_cvs(
    folder_id: str, 
    google_token: Optional[str] = Header(None, alias="X-Drive-Token"),
    user: dict = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    if not google_token:
        raise HTTPException(status_code=401, detail="Token de Google requerido")
    try:
        if not drive_service.build_service(google_token):
            raise HTTPException(status_code=500, detail="Error conectando con Drive")
        
        all_files = drive_service.list_files_in_folder(folder_id, None, recursive=True)
        if not all_files:
            return {"success": True, "processed": 0, "message": "La carpeta está vacía."}
            
        file_types = ['application/pdf']
        files = [f for f in all_files if f.get('mimeType') in file_types]
        
        if not files:
            mimes = set([f.get('mimeType') for f in all_files])
            raise HTTPException(status_code=400, detail=f"No hay PDFs en la carpeta. Tipos encontrados: {mimes}")
            
        print(f"Procesando {len(files)} CVs...")

        procesamiento = crud.create_procesamiento(db, folder_id=folder_id, folder_type='cvs', files_total=len(files))
        processed_cvs = []
        errors = []

        semaphore = asyncio.Semaphore(2)

        async def process_single_cv(idx, file):
            async with semaphore:
                try:
                    print(f"  ...Iniciando CV ({idx+1}/{len(files)}): {file['name']}")
                    
                    # RETRY LOGIC PARA DESCARGA (3 intentos) + THREAD SAFE
                    max_retries = 3
                    file_content = None
                    last_error = None
                    
                    for attempt in range(max_retries):
                        try:
                            loop = asyncio.get_event_loop()
                            if attempt > 0: await asyncio.sleep(1 * attempt)
                            # USAR MÉTODO THREAD-SAFE
                            file_content = await loop.run_in_executor(None, drive_service.download_file_thread_safe, file['id'], google_token)
                            if file_content: break
                        except Exception as e:
                            last_error = e
                            print(f"Retry {attempt+1}/{max_retries} descarga {file['name']}: {e}")
                    
                    if not file_content:
                        return {'error': f'Fallo descarga tras {max_retries} intentos: {last_error}', 'file': file}

                    # Procesamiento CPU-bound
                    cv_info = await loop.run_in_executor(None, pdf_processor.extract_cv_info, file_content, file['name'])
                    
                    if cv_info['success']:
                        docente_id = pdf_processor.save_docente_to_db(db, cv_info, file['id'])
                        if docente_id:
                            crud.update_procesamiento_progress(db, procesamiento.id, idx + 1)
                            return {'success': True, 'docente_id': docente_id}
                        else:
                            return {'error': 'Error al guardar en BD', 'file': file}
                    else:
                        return {'error': cv_info.get('error'), 'file': file}
                        
                except Exception as e:
                    return {'error': str(e), 'file': file}

        # Lanzar tareas
        tasks = [process_single_cv(i, f) for i, f in enumerate(files)]
        results = await asyncio.gather(*tasks)

        # Procesar resultados
        for res in results:
            if res.get('success'):
                d = crud.get_docente_by_id(db, res['docente_id'])
                if d: processed_cvs.append(d)
            else:
                errors.append({'filename': res['file']['name'], 'error': res['error']})
        
        if errors:
            crud.mark_procesamiento_error(db, procesamiento.id, f"{len(errors)} errores")
        
        crud.clear_recomendaciones_cache(db) # Invalidar cache
        
        return {
            "success": True,
            "processed": len(processed_cvs),
            "errors": len(errors),
            "docentes": [d.to_dict() if hasattr(d, 'to_dict') else d.__dict__ for d in processed_cvs],
            "error_details": errors
        }
    except Exception as e:
        print(f"❌ Error procesando CVs: {e}")
        raise HTTPException(status_code=500, detail=f"Error procesando CVs: {str(e)}")

# B. PROCESAR SÍLABOS
@app.post("/api/drive/process-syllabi/{folder_id}")
async def process_syllabi(
    folder_id: str, 
    google_token: Optional[str] = Header(None, alias="X-Drive-Token"),
    user: dict = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    if not google_token:
        raise HTTPException(status_code=401, detail="Token de Google requerido")
    try:
        if not drive_service.build_service(google_token):
            raise HTTPException(status_code=500, detail="Error conectando con Drive")
        
        all_files = drive_service.list_files_in_folder(folder_id, None, recursive=True)
        if not all_files:
            return {"success": True, "processed": 0, "message": "La carpeta está vacía."}
            
        file_types = ['application/vnd.openxmlformats-officedocument.wordprocessingml.document']
        files = [f for f in all_files if f.get('mimeType') in file_types]
        
        if not files:
            mimes = set([f.get('mimeType') for f in all_files])
            raise HTTPException(status_code=400, detail=f"No hay Word Docx en la carpeta. Tipos encontrados: {mimes}")
            
        print(f"📚 Procesando {len(files)} sílabos...")

        procesamiento = crud.create_procesamiento(db, folder_id=folder_id, folder_type='syllabi', files_total=len(files))
        processed_cursos = []
        errors = []

        semaphore = asyncio.Semaphore(2)

        async def process_single_syllabus(idx, file):
            async with semaphore:
                try:
                    loop = asyncio.get_event_loop()
                    print(f"  ...Iniciando Sílabo ({idx+1}/{len(files)}): {file['name']}")
                    
                    # OPTIMIZACIÓN: Verificar si ya existe en BD para saltar descarga y AI
                    # Esto permite reanudar procesos interrumpidos sin gastar quota
                    existing_curso = await loop.run_in_executor(None, crud.get_curso_by_drive_id, db, file['id'])
                    if existing_curso:
                        print(f"    ⏩ Saltando {file['name']} (Ya procesado)")
                        return {'success': True, 'curso_id': existing_curso.id}
                    
                    max_retries = 3
                    file_content = None
                    last_error = None
                    
                    for attempt in range(max_retries):
                        try:
                            loop = asyncio.get_event_loop()
                            if attempt > 0: await asyncio.sleep(1 * attempt)
                            # DEBUG: Verificar si entra aquí
                            print(f"    ⬇️ Intentando descargar {file['name']} (Intento {attempt+1})")
                            # USAR MÉTODO THREAD-SAFE
                            file_content = await loop.run_in_executor(None, drive_service.download_file_thread_safe, file['id'], google_token)
                            if file_content: break
                        except Exception as e:
                            last_error = e
                            print(f"    ⚠️ Retry {attempt+1}/{max_retries} descarga {file['name']}: {e}")

                    if not file_content:
                        return {'error': f'Fallo descarga tras {max_retries} intentos: {last_error}', 'file': file}

                    syllabus_info = await loop.run_in_executor(None, docx_processor.extract_syllabus_info, file_content, file['name'])
                    
                    if syllabus_info['success']:
                        curso_id = docx_processor.save_curso_to_db(db, syllabus_info, file['id'])
                        if curso_id:
                            crud.update_procesamiento_progress(db, procesamiento.id, idx + 1)
                            return {'success': True, 'curso_id': curso_id}
                        else:
                            return {'error': 'Error al guardar en BD', 'file': file}
                    else:
                        return {'error': syllabus_info.get('error'), 'file': file}
                        
                except Exception as e:
                    print(f"    ❌ Error en {file['name']}: {e}")
                    return {'error': str(e), 'file': file}

        tasks = [process_single_syllabus(i, f) for i, f in enumerate(files)]
        results = await asyncio.gather(*tasks)

        for res in results:
            if res.get('success'):
                c = crud.get_curso_by_id(db, res['curso_id'])
                if c: processed_cursos.append(c)
            else:
                errors.append({'filename': res['file']['name'], 'error': res['error']})

        if errors:
            crud.mark_procesamiento_error(db, procesamiento.id, f"{len(errors)} errores")

        crud.clear_recomendaciones_cache(db)

        ciclos_cursos = {}
        for curso in processed_cursos:
            ciclo_str = str(curso.ciclo or 1)
            if ciclo_str not in ciclos_cursos:
                ciclos_cursos[ciclo_str] = []
            
            # Crear objeto simple para evitar errores de serialización
            curso_obj = {
                "id": curso.id,
                "nombre": curso.nombre,
                "codigo": curso.codigo,
                "ciclo": curso.ciclo
            }
            ciclos_cursos[ciclo_str].append(curso_obj)
        
        return {
            "success": True,
            "processed": len(processed_cursos),
            "errors": len(errors),
            "ciclos": sorted(ciclos_cursos.keys(), key=lambda x: int(x) if x.isdigit() else 99),
            "cursos_por_ciclo": ciclos_cursos,
            "error_details": errors
        }
    except Exception as e:
        print(f"❌ Error procesando sílabos: {e}")
        raise HTTPException(status_code=500, detail=f"Error procesando sílabos: {str(e)}")

# C. PROCESAR HORARIOS (¡LA PARTE NUEVA!)
@app.post("/api/drive/process-schedules/{folder_id}")
async def process_schedules(
    folder_id: str, 
    google_token: Optional[str] = Header(None, alias="X-Drive-Token"),
    user: dict = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    if not google_token:
        raise HTTPException(status_code=401, detail="Token de Google requerido")

    try:
        if not drive_service.build_service(google_token):
            raise HTTPException(status_code=500, detail="Error conectando con Drive")
        
        # Buscar PDFs de horarios
        all_files = drive_service.list_files_in_folder(folder_id, None, recursive=True)
        if not all_files:
            return {"success": True, "processed": 0, "message": "La carpeta está vacía."}
            
        file_types = ['application/pdf']
        files = [f for f in all_files if f.get('mimeType') in file_types]
        
        if not files:
            mimes = set([f.get('mimeType') for f in all_files])
            raise HTTPException(status_code=400, detail=f"No hay PDFs en la carpeta. Tipos encontrados: {mimes}")
            
        print(f"📅 Procesando {len(files)} horarios...")

        procesamiento = crud.create_procesamiento(db, folder_id=folder_id, folder_type='schedules', files_total=len(files))
        
        total_records = 0
        errors = []

        semaphore = asyncio.Semaphore(2)

        async def process_single_schedule(idx, file):
            async with semaphore:
                try:
                    print(f"  ...Iniciando Horario ({idx+1}/{len(files)}): {file['name']}")
                    
                    max_retries = 3
                    file_content = None
                    last_error = None
                    
                    for attempt in range(max_retries):
                        try:
                            loop = asyncio.get_event_loop()
                            if attempt > 0: await asyncio.sleep(1 * attempt)
                            # USAR MÉTODO THREAD-SAFE
                            file_content = await loop.run_in_executor(None, drive_service.download_file_thread_safe, file['id'], google_token)
                            if file_content: break
                        except Exception as e:
                            last_error = e
                            print(f"    ⚠️ Retry {attempt+1}/{max_retries} descarga {file['name']}: {e}")

                    if not file_content: return {'records': 0}

                    # Guardar contenido en archivo temporal
                    import tempfile
                    import os
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                        tmp_file.write(file_content)
                        tmp_path = tmp_file.name
                    
                    real_name_path = None
                    try:
                        temp_dir = os.path.dirname(tmp_path)
                        real_name_path = os.path.join(temp_dir, file['name'].replace("/", "_"))
                        
                        if os.path.exists(real_name_path): os.remove(real_name_path)
                        os.rename(tmp_path, real_name_path)
                        
                        # Ejecutar extracción en executor (CPU bound + I/O)
                        extracted_data = await loop.run_in_executor(None, schedule_processor.extract_schedule_data, real_name_path)
                        
                        # Guardar en BD (Síncrono)
                        records_saved = schedule_processor.save_history_to_db(db, extracted_data)
                        
                        crud.update_procesamiento_progress(db, procesamiento.id, idx + 1)
                        return {'records': records_saved}
                        
                    finally:
                        if real_name_path and os.path.exists(real_name_path): os.remove(real_name_path)
                        if os.path.exists(tmp_path): os.remove(tmp_path)
                        
                except Exception as e:
                    print(f"  ❌ Error en horario {file['name']}: {e}")
                    return {'error': str(e), 'file': file}

        tasks = [process_single_schedule(i, f) for i, f in enumerate(files)]
        results = await asyncio.gather(*tasks)

        for res in results:
            if 'records' in res:
                total_records += res['records']
            elif 'error' in res:
                errors.append({'filename': res['file']['name'], 'error': res['error']})

        if errors:
            crud.mark_procesamiento_error(db, procesamiento.id, f"{len(errors)} errores")
        
        # Limpiar cache porque el historial afecta al ranking
        crud.clear_recomendaciones_cache(db)

        return {
            "success": True,
            "processed_files": len(files),
            "total_history_records": total_records,
            "errors": len(errors),
            "error_details": errors
        }
        
    except Exception as e:
        print(f"❌ Error procesando horarios: {e}")
        raise HTTPException(status_code=500, detail=f"Error procesando horarios: {str(e)}")

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

# --- 9. ENDPOINTS DE DEBUG (PARA VERIFICAR NER) ---
@app.get("/api/debug/ner-profile/docente/{docente_id}")
async def debug_docente_ner_profile(docente_id: int, db: Session = Depends(get_db)):
    docente = crud.get_docente_by_id(db, docente_id)
    if not docente:
        raise HTTPException(status_code=404, detail="Docente no encontrado")
    
    # Volver a ejecutar NER en el texto actual para ver qué detecta el diccionario actual
    full_text = docente.cv_text
    entities = extract_entities(full_text)
    profile_text = recommendation_engine.create_docente_text(docente)
    
    return {
        "success": True,
        "docente_id": docente_id,
        "docente_nombre": docente.nombre,
        "perfil_ner_extraido_con_diccionario_actual": entities,
        "texto_que_usa_sbert": profile_text,
        "texto_completo_original (preview)": full_text[:1000] if full_text else "N/A"
    }

@app.get("/api/debug/ner-profile/curso/{curso_id}")
async def debug_curso_ner_profile(curso_id: int, db: Session = Depends(get_db)):
    curso = crud.get_curso_by_id(db, curso_id)
    if not curso:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    
    full_text = curso.syllabus_text
    entities = extract_entities(full_text)
    profile_text = recommendation_engine.create_curso_text(curso)
    
    return {
        "success": True,
        "curso_id": curso_id,
        "curso_nombre": curso.nombre,
        "perfil_ner_extraido_con_diccionario_actual": entities,
        "texto_que_usa_sbert": profile_text,
        "texto_completo_original (preview)": full_text[:1000] if full_text else "N/A"
    }

# --- EJECUCIÓN LOCAL O CLOUD RUN ---
if __name__ == "__main__":
    import uvicorn
    # Cloud Run inyecta la variable de entorno PORT, por defecto usamos 8080 si no existe
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 Servidor iniciando en http://0.0.0.0:{port} ...")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port)