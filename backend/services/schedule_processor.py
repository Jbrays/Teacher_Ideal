import re
import logging
import pdfplumber
from io import BytesIO
import os
import json
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session
import concurrent.futures

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
        self.location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-3.1-flash-lite")
        
        try:
            vertexai.init(project=self.project_id, location=self.location)
            self.model = GenerativeModel(self.model_name)
            logger.info(f"Vertex AI inicializado correctamente con modelo: {self.model_name}")
        except Exception as e:
            logger.error(f"Error inicializando Vertex AI: {e}", exc_info=True)
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
                
                logger.info(f"📄 Total páginas: {total_pages} | Batch Size: {batch_size}")
                
                # PREPARAR BLOQUES DE TEXTO
                bloques = []
                for i in range(0, total_pages, batch_size):
                    batch_pages = pdf.pages[i : i + batch_size]
                    batch_text = ""
                    for idx, page in enumerate(batch_pages):
                        text = page.extract_text(layout=True) or ""
                        batch_text += f"\n--- PÁGINA {i + idx + 1} ---\n{text}\n"
                    bloques.append((i // batch_size + 1, batch_text))
                    
                MAX_WORKERS = 5
                import random
                import time
                
                def _procesar_bloque(batch_idx, batch_text):
                    prompt = f"""
Eres un extractor de datos de horarios universitarios.
Solo extraes lo que está literalmente en el documento.

ALGORITMO DE LECTURA:
1. El período académico está en el encabezado del documento. 
   Captúralo una sola vez y aplícalo a todos los registros.
2. Por cada curso encuentra: el nombre del curso y el nombre del docente.
3. Un curso puede aparecer en múltiples líneas. Consolida en un solo 
   registro por combinación única de docente y curso.
4. Ignora completamente cualquier fila donde el docente sea "STAFF".

REGLAS:
- Extrae el nombre del curso tal cual aparece en el documento.
- Extrae el nombre del docente tal cual aparece en el documento.
- El período es el código numérico del ciclo académico del encabezado.
- Si un mismo docente dicta el mismo curso en varias secciones, 
  es un solo registro.
- No extraigas NRC, sección, aula, hora, créditos ni ningún otro dato.

Devuelve ÚNICAMENTE este JSON sin prefijos ni etiquetas:
[
  {{
    "nombre_docente": "string",
    "curso": "string",
    "periodo": "string"
  }}
]

DOCUMENTO:
{batch_text}
"""
                    max_retries = 5
                    for attempt in range(max_retries):
                        try:
                            # Rate limiting preventivo
                            if attempt > 0: time.sleep((attempt + 1) * 5 + random.uniform(0, 3))
                            else: time.sleep(1) # Pequeña pausa inicial
                            
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
                                
                            batch_results = []
                            for d in data:
                                if not d.get('nombre_docente') or not d.get('curso'):
                                    continue
                                if not d.get('periodo') or d.get('periodo') == "string":
                                    d['periodo'] = global_period
                                batch_results.append(d)
                            return batch_results
                            
                        except Exception as e:
                            error_str = str(e)
                            if "429" in error_str or "Resource exhausted" in error_str:
                                wait_time = 10 + random.uniform(2, 5)
                                logger.warning(f"⚠️ Quota (429) en Batch {batch_idx}. Reintentando en {wait_time:.1f}s... ({attempt+1}/{max_retries})")
                                time.sleep(wait_time)
                            elif "503" in error_str or "Handshake read failed" in error_str:
                                logger.warning(f"⚠️ Error 503 en Batch {batch_idx}. Reintentando... ({attempt+1}/{max_retries})")
                                time.sleep(5)
                            else:
                                if attempt == max_retries - 1:
                                    logger.error(f"⚠️ Error fatal en Batch {batch_idx}: {e}", exc_info=True)
                                    return []
                    return []

                # EJECUCIÓN MULTIHILOS
                workers_actuales = min(MAX_WORKERS, len(bloques))
                logger.info(f"🚀 Lanzando {len(bloques)} bloques en paralelo usando {workers_actuales} workers...")
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=workers_actuales) as executor:
                    futuros = {
                        executor.submit(_procesar_bloque, b[0], b[1]): b[0]
                        for b in bloques
                    }
                    
                    for futuro in concurrent.futures.as_completed(futuros):
                        idx = futuros[futuro]
                        try:
                            resultados_bloque = futuro.result(timeout=130.0)
                            all_results.extend(resultados_bloque)
                        except concurrent.futures.TimeoutError:
                            logger.error(f"⏱️ TIMEOUT FATAL: Batch {idx} no respondió tras 130s")
                        except Exception as e:
                            logger.error(f"❌ Error catastrófico atrapando futuro del Batch {idx}: {e}", exc_info=True)

            logger.info(f"✅ Vertex AI extrajo {len(all_results)} registros totales.")
            return all_results

        except Exception as e:
            logger.error(f"❌ Error procesando PDF con Vertex AI: {e}", exc_info=True)
            return []

    def save_history_to_db(self, db: Session, data: List[Dict]) -> int:
        """
        Guarda los datos y actualiza el historial.
        OPTIMIZACIÓN: Carga todos los docentes y cursos en memoria una sola vez
        para evitar consultas repetitivas dentro del bucle.
        """
        logger.info(f'save_history_to_db recibió {len(data)} registros')
        if not data:
            return 0
            
        count = 0
        
        try:
            aggregated_entries = {}

            for item in data:
                docente_nombre = item.get('nombre_docente', '').strip().upper()
                curso_nombre = item.get('curso', '').strip().upper()
                
                if not docente_nombre or not curso_nombre: 
                    continue
                
                # Clave única para agregación en este lote
                key = (docente_nombre, curso_nombre, item['periodo'])
                
                if key in aggregated_entries:
                    aggregated_entries[key] += 1
                else:
                    aggregated_entries[key] = 1

            # --- 3. GUARDADO EN BD (UPSERT Súper Lean) ---
            for (doc_nombre, c_nombre, per), veces_count in aggregated_entries.items():
                existing = db.query(Historial).filter(
                    Historial.nombre_docente == doc_nombre,
                    Historial.nombre_curso == c_nombre
                ).first()
                
                if existing:
                    existing.veces += veces_count
                    if per > existing.ultima_vez:
                        existing.ultima_vez = per
                    db.add(existing)
                else:
                    new_entry = Historial(
                        nombre_docente=doc_nombre,
                        nombre_curso=c_nombre,
                        veces=veces_count,
                        ultima_vez=per
                    )
                    db.add(new_entry)
                    count += 1
            
            db.commit()
            logger.info(f"💾 Commit exitoso: {count} nuevos registros de historial insertados (plano).")
            return count

        except Exception as e:
            db.rollback()
            logger.error(f"❌ Error en transaccion de historial: {e}", exc_info=True)
            return 0

schedule_processor = ScheduleProcessor()