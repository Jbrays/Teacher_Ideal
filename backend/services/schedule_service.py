import re
import logging
import pdfplumber
import os
import time
import random
import concurrent.futures
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

# Import Vertex AI (Gemini) directly for batching as it was done before,
# or we could use GeminiClient. But since it does multithreading, thread safety 
# with GeminiClient (which uses asyncio inside) might be tricky in pure threads. 
# The previous code used synchronous generate_content. I'll keep the synchronous 
# google.generativeai or vertexai logic to not break the multithreading batcher.
import vertexai
from vertexai.generative_models import GenerativeModel

from backend.repositories.historial_repo import HistorialRepository
from backend.llm.prompts.schedule import prompt_horarios

logger = logging.getLogger(__name__)

class ScheduleService:
  """
  Servicio de orquestación para extracción de horarios académicos de la UPAO.
  Optimizado con procesamiento multihilos y persistencia limpia.
  """

  def __init__(self, db: Session):
    self.db = db
    self.historial_repo = HistorialRepository(db)
    
    self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "semilleros-493300")
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
    match = re.search(r'(20\d{2})[-_\s]?(10|20)', filename)
    if match:
      return f"{match.group(1)}-{match.group(2)}"
    return None

  def _extract_periodo_from_text(self, text: str) -> str:
    """Busca patrones de periodo en el texto del encabezado."""
    match_num = re.search(r'(20\d{2})[-_\s]?(10|20)', text)
    if match_num:
      return f"{match_num.group(1)}-{match_num.group(2)}"
      
    match_roman = re.search(r'(20\d{2})[-_\s]?(I{1,2})', text, re.IGNORECASE)
    if match_roman:
      year = match_roman.group(1)
      cycle_roman = match_roman.group(2).upper()
      cycle = "10" if cycle_roman == "I" else "20"
      return f"{year}-{cycle}"
      
    return "HISTORICO"

  def extract_schedule_data(self, pdf_path: str, filename: str) -> List[Dict]:
    """
    Extrae la información del horario usando Vertex AI (Gemini) por lotes de páginas.
    """
    if not self.model:
      logger.error(" Modelo Vertex AI no disponible.")
      return []

    logger.info(f" Procesando horario con Vertex AI (Batching): {filename}")
    all_results = []
    
    try:
      global_period = self._extract_periodo_from_filename(filename)
      
      with pdfplumber.open(pdf_path) as pdf:
        if not global_period:
          logger.info(" Periodo no encontrado en nombre de archivo. Buscando en contenido...")
          if len(pdf.pages) > 0:
            first_page_text = pdf.pages[0].extract_text() or ""
            global_period = self._extract_periodo_from_text(first_page_text)
          else:
            global_period = "HISTORICO"
        
        logger.info(f" Periodo Global detectado: {global_period}")

        total_pages = len(pdf.pages)
        batch_size = 5 
        
        logger.info(f" Total páginas: {total_pages} | Batch Size: {batch_size}")
        
        bloques = []
        for i in range(0, total_pages, batch_size):
          batch_pages = pdf.pages[i : i + batch_size]
          batch_text = ""
          for idx, page in enumerate(batch_pages):
            text = page.extract_text(layout=True) or ""
            batch_text += f"\n--- PÁGINA {i + idx + 1} ---\n{text}\n"
          bloques.append((i // batch_size + 1, batch_text))
          
        MAX_WORKERS = 5
        
        def _procesar_bloque(batch_idx, batch_text):
          prompt = prompt_horarios(batch_text)
          max_retries = 5
          for attempt in range(max_retries):
            try:
              if attempt > 0: time.sleep((attempt + 1) * 5 + random.uniform(0, 3))
              else: time.sleep(1) 
              
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
                logger.warning(f" Quota (429) en Batch {batch_idx}. Reintentando en {wait_time:.1f}s... ({attempt+1}/{max_retries})")
                time.sleep(wait_time)
              elif "503" in error_str or "Handshake read failed" in error_str:
                logger.warning(f" Error 503 en Batch {batch_idx}. Reintentando... ({attempt+1}/{max_retries})")
                time.sleep(5)
              else:
                if attempt == max_retries - 1:
                  logger.error(f" Error fatal en Batch {batch_idx}: {e}", exc_info=True)
                  return []
          return []

        workers_actuales = min(MAX_WORKERS, len(bloques))
        logger.info(f" Lanzando {len(bloques)} bloques en paralelo usando {workers_actuales} workers...")
        
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
              logger.error(f" TIMEOUT FATAL: Batch {idx} no respondió tras 130s")
            except Exception as e:
              logger.error(f" Error catastrófico atrapando futuro del Batch {idx}: {e}", exc_info=True)

      logger.info(f" Vertex AI extrajo {len(all_results)} registros totales.")
      return all_results

    except Exception as e:
      logger.error(f" Error procesando PDF con Vertex AI: {e}", exc_info=True)
      return []

  def _save_history_to_db(self, data: List[Dict], propietario_email: str = "legacy@upao.edu.pe") -> int:
    """
    Guarda los datos en la base de datos usando HistorialRepository.
    Realiza una agregación en memoria por seguridad, pero delega el upsert.
    """
    logger.info(f'Guardando {len(data)} registros de historial en BD')
    if not data:
      return 0
      
    count = 0
    try:
      # Agregamos en memoria para tener el periodo máximo (ultima_vez) por combinación
      aggregated_entries = {}

      for item in data:
        docente_nombre = item.get('nombre_docente', '').strip().upper()
        curso_nombre = item.get('curso', '').strip().upper()
        periodo = item.get('periodo', '').strip()
        
        if not docente_nombre or not curso_nombre or not periodo: 
          continue
        
        key = (docente_nombre, curso_nombre)
        if key not in aggregated_entries or periodo > aggregated_entries[key]:
          aggregated_entries[key] = periodo

      for (doc_nombre, c_nombre), max_per in aggregated_entries.items():
        self.historial_repo.upsert(
          nombre_docente=doc_nombre,
          nombre_curso=c_nombre,
          periodo=max_per,
          propietario_email=propietario_email,
        )
        count += 1
      
      self.db.commit()
      logger.info(f" Commit exitoso: {count} registros de historial procesados.")
      return count

    except Exception as e:
      self.db.rollback()
      logger.error(f" Error guardando historial: {e}", exc_info=True)
      return 0

  def extract_and_save(self, pdf_path: str, filename: str, propietario_email: str = "legacy@upao.edu.pe") -> bool:
    """
    Flujo completo: Extracción y guardado.
    """
    data_list = self.extract_schedule_data(pdf_path, filename)
    if data_list:
      registros = self._save_history_to_db(data_list, propietario_email=propietario_email)
      return registros > 0
    return False
