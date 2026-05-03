import re
import logging
import pdfplumber
from io import BytesIO
import os
import json
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session

# Vertex AI Imports
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from google.oauth2 import service_account

# Configuración de Logging 
logger = logging.getLogger(__name__)

# Intentamos importar los modelos. 
# Usamos un bloque try para que el procesador no rompa la app si falla la importación al inicio.
try:
    from backend.database.models import Historial, Docente, Curso
except ImportError:
    logger.critical("Error crítico: No se pudieron importar los modelos de BD (Historial, Docente, Curso).")
    Historial, Docente, Curso = None, None, None

class ScheduleProcessor:
    """
    Procesa PDFs de horarios académicos de la UPAO.
    Optimizado para evitar consultas N+1 a la base de datos.
    """

    def __init__(self):
        # Configuración de Vertex AI
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        self.model_name = "gemini-3.1-flash-lite-preview"
        
        try:
            vertexai.init(project=self.project_id, location=self.location)
            self.model = GenerativeModel(self.model_name)
            logger.info(f"Vertex AI inicializado correctamente con modelo: {self.model_name}")
        except Exception as e:
            logger.error(f"Error inicializando Vertex AI: {e}")
            self.model = None

    def _extract_periodo_from_filename(self, filename: str) -> str:
        """Intenta extraer el periodo del nombre del archivo (ej: 2024-10)."""
        # Soporta: 2024-10, 2024 10, 202410, 2024-1, 2024 1
        # FIX: Restringir ciclo a 10 o 20 (evita confundir con fechas como 2024-08)
        match = re.search(r'(20\d{2})[-_\s]?(10|20)', filename)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
        return None # Retornamos None para indicar fallo

    def _extract_periodo_from_text(self, text: str) -> str:
        """Busca patrones de periodo en el texto del encabezado."""
        # Patrones comunes en encabezados: "SEMESTRE 2024-10", "CICLO 2024 20", "2024-I", "2024-II"
        
        # 1. Formato numérico estándar: 2024-10, 2024 20, 202410
        # FIX: Restringir ciclo a 10 o 20
        match_num = re.search(r'(20\d{2})[-_\s]?(10|20)', text)
        if match_num:
            return f"{match_num.group(1)}-{match_num.group(2)}"
            
        # 2. Formato Romano: 2024-I, 2024-II, 2024 I, 2024 II
        match_roman = re.search(r'(20\d{2})[-_\s]?(I{1,2})', text, re.IGNORECASE)
        if match_roman:
            year = match_roman.group(1)
            cycle_roman = match_roman.group(2).upper()
            cycle = "10" if cycle_roman == "I" else "20"
            return f"{year}-{cycle}"
            
        return "HISTORICO"

    def extract_schedule_data(self, pdf_path: str) -> List[Dict]:
        """
        Extrae la información del horario usando Vertex AI (Gemini) por lotes de páginas.
        Optimización: Procesa 3 páginas por request para reducir tiempo y llamadas API.
        """
        if not self.model:
            logger.error("❌ Modelo Vertex AI no disponible.")
            return []

        filename = os.path.basename(pdf_path)
        logger.info(f"🚀 Procesando horario con Vertex AI (Batching): {filename}")
        all_results = []
        
        try:
            import time
            
            # 1. Determinar Periodo Global
            # Estrategia A: Nombre del archivo
            global_period = self._extract_periodo_from_filename(filename)
            
            with pdfplumber.open(pdf_path) as pdf:
                # Estrategia B: Si falla nombre, buscar en primera página
                if not global_period:
                    logger.info("⚠️ Periodo no encontrado en nombre de archivo. Buscando en contenido...")
                    if len(pdf.pages) > 0:
                        first_page_text = pdf.pages[0].extract_text() or ""
                        global_period = self._extract_periodo_from_text(first_page_text)
                    else:
                        global_period = "HISTORICO"
                
                logger.info(f"📅 Periodo Global detectado: {global_period}")

                total_pages = len(pdf.pages)
                batch_size = 5 # Aumentado a 5 para reducir llamadas API
                
                print(f"📄 Total páginas: {total_pages} | Batch Size: {batch_size}")
                
                for i in range(0, total_pages, batch_size):
                    # Construir lote
                    batch_pages = pdf.pages[i : i + batch_size]
                    batch_text = ""
                    for idx, page in enumerate(batch_pages):
                        text = page.extract_text(layout=True) or ""
                        batch_text += f"\n--- PÁGINA {i + idx + 1} ---\n{text}\n"
                    
                    print(f"   ⏳ Procesando Batch {i//batch_size + 1}/{(total_pages + batch_size - 1)//batch_size} (Págs {i+1}-{min(i+batch_size, total_pages)})...")
                    
                    prompt = f"""
                    Analiza este TEXTO extraído de varias páginas de un horario universitario.
                    Extrae TODAS las asignaciones de cursos a docentes basándote EXCLUSIVAMENTE en códigos.
                    
                    TEXTO DEL LOTE:
                    {batch_text}
                    
                    Reglas:
                    1. Ignora "STAFF" o "DOCENTE" genérico.
                    2. Extrae estrictamente el CÓDIGO institucional del curso (ej: "ICSI424").
                    3. Extrae estrictamente el CÓDIGO ÚNICO del docente (ID_DOC).
                    4. IGNORA el periodo del texto, usaremos uno global.
                    
                    Salida JSON (Lista de objetos estricta):
                    [
                        {{"curso_codigo": "ICSI424", "docente_id": "000123"}}
                    ]
                    """
                    
                    # RETRY LOGIC PARA VERTEX AI (429, 503 & JSON Errors)
                    import random
                    max_retries = 5 # Aumentado a 5 intentos
                    for attempt in range(max_retries):
                        try:
                            # Rate limiting preventivo con Jitter
                            base_wait = (attempt + 1) * 5
                            jitter = random.uniform(0, 3)
                            if attempt > 0: time.sleep(base_wait + jitter)
                            else: time.sleep(2)

                            response = self.model.generate_content(
                                prompt,
                                generation_config={
                                    "response_mime_type": "application/json",
                                    "temperature": 0.1,
                                    "max_output_tokens": 8192
                                }
                            )
                            
                            json_text = response.text.replace("```json", "").replace("```", "").strip()
                            data = json.loads(json_text)
                            
                            if isinstance(data, dict):
                                if "asignaciones" in data: data = data["asignaciones"]
                                else: data = [data]
                                
                            # Procesar y limpiar datos del lote
                            for d in data:
                                if not d.get('docente_id') or not d.get('curso_codigo'):
                                    continue
                                
                                # FORZAR PERIODO GLOBAL
                                d['periodo'] = global_period
                                all_results.append(d)
                            
                            break # Éxito, salir del retry loop
                            
                        except Exception as e:
                            error_str = str(e)
                            is_503 = "503" in error_str or "Handshake read failed" in error_str or "FD Shutdown" in error_str or "Socket closed" in error_str
                            is_429 = "429" in error_str or "Resource exhausted" in error_str
                            
                            if is_429 or is_503:
                                # Backoff más agresivo para errores de conexión/quota
                                wait_time = (attempt + 1) * 15 + random.uniform(0, 5) # 15s, 30s, 45s...
                                err_type = "Quota (429)" if is_429 else "Connection (503)"
                                logger.warning(f"⚠️ {err_type} en Batch {i//batch_size + 1}. Reintentando en {wait_time:.1f}s... ({attempt+1}/{max_retries})")
                                time.sleep(wait_time)
                            elif "Unterminated string" in error_str or "Expecting value" in error_str:
                                logger.warning(f"⚠️ Error JSON en Batch {i//batch_size + 1}: {e}. Reintentando... ({attempt+1}/{max_retries})")
                            else:
                                logger.error(f"⚠️ Error en Batch {i//batch_size + 1}: {e}")
                                # Si no es recuperable, seguimos (o reintentamos si queda chance)
                                if attempt == max_retries - 1: pass

            logger.info(f"✅ Vertex AI extrajo {len(all_results)} registros totales.")
            return all_results

        except Exception as e:
            logger.error(f"❌ Error procesando PDF con Vertex AI: {e}")
            return []

    def save_history_to_db(self, db: Session, data: List[Dict]) -> int:
        """
        Guarda los datos y actualiza el historial.
        OPTIMIZACIÓN: Carga todos los docentes y cursos en memoria una sola vez
        para evitar consultas repetitivas dentro del bucle.
        """
        if not data:
            return 0
            
        count = 0
        
        try:
            # --- 1. PRE-FETCHING (Optimización Clave) ---
            logger.info("⏳ Precargando catálogo de docentes y cursos para comparación rápida...")
            all_docentes = db.query(Docente).all()
            all_cursos = db.query(Curso).all()
            
            # Convertimos a diccionarios para búsqueda O(1) usando los códigos exactos
            docentes_cache = {d.id_upao: d for d in all_docentes if d.id_upao}
            cursos_cache = {c.codigo: c for c in all_cursos if c.codigo}
            
            logger.info(f"📚 Catálogo indexado: {len(docentes_cache)} docentes con ID_DOC, {len(cursos_cache)} cursos con código.")

            aggregated_entries = {}

            for item in data:
                docente = docentes_cache.get(item.get('docente_id'))
                curso = cursos_cache.get(item.get('curso_codigo'))
                
                if not docente or not curso: 
                    continue
                
                # Clave única para agregación
                key = (docente.id, curso.id, item['periodo'])
                
                if key in aggregated_entries:
                    aggregated_entries[key] += 1
                else:
                    aggregated_entries[key] = 1

            # --- 3. GUARDADO EN BD ---
            for (doc_id, cur_id, per), veces_count in aggregated_entries.items():
                existing = db.query(Historial).filter(
                    Historial.docente_id == doc_id,
                    Historial.curso_id == cur_id,
                    Historial.periodo == per
                ).first()
                
                if existing:
                    existing.veces += veces_count
                    db.add(existing)
                else:
                    new_entry = Historial(
                        docente_id=doc_id,
                        curso_id=cur_id,
                        periodo=per,
                        resultado="Asignado en Horario",
                        veces=veces_count
                    )
                    db.add(new_entry)
                    count += 1
            
            db.commit()
            logger.info(f"💾 Commit exitoso: {count} nuevos registros de historial insertados (con agregación determinista).")
            return count

        except Exception as e:
            db.rollback()
            logger.error(f"❌ Error en transaccion de historial: {e}")
            return 0

schedule_processor = ScheduleProcessor()