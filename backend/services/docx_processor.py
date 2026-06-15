import logging
import json
import os
import asyncio
import random
import re
from pathlib import Path
from typing import Dict, Optional, List
from docx import Document
from io import BytesIO
from sqlalchemy.orm import Session
from google import genai
from google.genai import types
from backend.services.entity_utils import run_async

logger = logging.getLogger(__name__)


def prompt_temas_silabo(texto_silabo: str) -> str:
    return f"""
Eres un extractor de información de sílabos universitarios. Solo usas lo que está
literalmente en el documento. No inventas ni condensas información.

TAREA:
Revisa la tabla de programación semanal del sílabo y extrae el contenido temático
de cada semana. La tabla suele tener columnas como "N° Semanas", "Contenidos Temáticos"
y "Actividades de Aprendizaje". Debes extraer SOLO la columna "Contenidos Temáticos".

REGLAS OBLIGATORIAS:
1. Revisa semana por semana. No saltes ninguna semana.
2. Extrae el contenido temático tal cual aparece, sin resumir.
3. Si una semana tiene varios temas, divídelos en items separados.
4. No inventes temas que no estén en el documento.
5. No condenses varias semanas en una sola.

OMITIR SIEMPRE:
- Semanas de evaluación: "Evaluación Parcial", "Evaluación Final", "Examen Sustitutorio"
- Semanas de retroalimentación
- Hitos de proyecto
- Foros participativos
- Semanas de actualización académica
- Presentación de proyectos
- Cualquier actividad que no sea contenido temático

FORMATO DE SALIDA:
Devuelve ÚNICAMENTE este JSON:
{{
  "nombre": "string",
  "codigo": "string",
  "ciclo": 0,
  "temas": ["string"]
}}

Si no hay temas extraíbles: "temas": [].

DOCUMENTO:
{texto_silabo}
"""


# Filtro de seguridad post-extracción: elimina items que no son contenido temático
PALABRAS_EXCLUIR = re.compile(
    r'evaluaci[oó]n|examen|parcial|final|sustitutorio|retroalimentaci[oó]n|'
    r'hito\s*\d|semana\s*de\s*actualizaci[oó]n|foro\s*participativo|'
    r'presentaci[oó]n\s*de\s*proyectos|informe\s*final|preparaci[oó]n\s*para',
    re.IGNORECASE
)


def filtrar_temas(temas: List[str]) -> List[str]:
    """Elimina items que no son contenido temático real."""
    filtrados = []
    for t in temas:
        if not t or not t.strip():
            continue
        t_limpio = t.strip()
        if PALABRAS_EXCLUIR.search(t_limpio):
            logger.info(f"Tema excluido por filtro: '{t_limpio[:80]}...'")
            continue
        filtrados.append(t_limpio)
    return filtrados


class DOCXProcessor:
    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        
        try:
            self.client = genai.Client(vertexai=True, project=self.project_id, location=self.location)
            logger.info(f"genai SDK inicializado en el proyecto {self.project_id} para DOCX")
        except Exception as e:
            logger.error(f"Error iniciando genai Client en DOCX: {e}", exc_info=True)
            self.client = None

    async def llamar_flash_lite(self, texto: str) -> dict:
        if not self.client: return {}
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    wait = 5 * (2 ** (attempt - 1)) + random.uniform(0, 2)
                    logger.warning(f"⏳ [Sílabo] Flash Lite retry {attempt+1}/{max_retries} en {wait:.1f}s...")
                    await asyncio.sleep(wait)
                start_time = time.time()
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model="gemini-3.1-flash-lite",
                        contents=prompt_temas_silabo(texto),
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.1
                        )
                    ),
                    timeout=120.0
                )
                elapsed = time.time() - start_time
                logger.info(f"⏱️ [Sílabo] Flash Lite tardó: {elapsed:.2f} segundos")
                try:
                    return json.loads(response.text.strip())
                except Exception as e:
                    logger.error(f"Error parseando Flash Lite (DOCX): {e}")
                    return {}
            except Exception as e:
                if ("429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)) and attempt < max_retries - 1:
                    continue
                logger.error(f"Error en Flash Lite Sílabo (intento {attempt+1}): {e}", exc_info=True)
                return {}

    async def procesar_silabo(self, texto_silabo: str) -> dict:
        return await self.llamar_flash_lite(texto_silabo)

    def extract_text_from_docx(self, docx_bytes: bytes) -> str:
        """Extrae todo el texto plano del DOCX, incluyendo tablas, respetando el orden real."""
        try:
            from docx.oxml.ns import qn
            doc = Document(BytesIO(docx_bytes))
            text = []

            for block in doc.element.body:
                # Párrafo normal
                if block.tag == qn('w:p'):
                    from docx.text.paragraph import Paragraph
                    p = Paragraph(block, doc)
                    if p.text.strip():
                        text.append(p.text)

                # Tabla
                elif block.tag == qn('w:tbl'):
                    from docx.table import Table
                    table = Table(block, doc)
                    for row in table.rows:
                        row_text = []
                        for cell in row.cells:
                            if cell.text.strip():
                                row_text.append(cell.text.strip())
                        if row_text:
                            text.append(" | ".join(row_text))

            return "\n".join(text)
        except Exception as e:
            logger.error(f"Error leyendo DOCX crudo: {e}", exc_info=True)
            return ""

    def extract_syllabus_info(self, docx_bytes: bytes, filename: str = "") -> Dict:
        try:
            # 1. Leer texto crudo
            full_text = self.extract_text_from_docx(docx_bytes)
            if not full_text:
                return {'success': False, 'error': 'DOCX vacío o ilegible'}

            logger.info(f"Extrayendo temas semanales del sílabo: {filename}")
            
            # 2. Extraer con Flash Lite
            ai_data = run_async(self.procesar_silabo(full_text))

            if not ai_data:
                return {'success': False, 'error': 'Fallo en extracción IA'}

            # Valores por defecto
            nombre = ai_data.get('nombre')
            if not nombre and filename:
                nombre = filename.replace('.docx', '').replace('_', ' ')

            temas_extraidos = ai_data.get('temas', [])
            temas_filtrados = filtrar_temas(temas_extraidos)
            logger.info(f"Temas extraídos: {len(temas_extraidos)} | Temas válidos: {len(temas_filtrados)}")
            
            return {
                'success': True,
                'nombre': nombre,
                'codigo': ai_data.get('codigo'),
                'ciclo': ai_data.get('ciclo', 1),
                'temas': temas_filtrados,
                'raw_text': full_text,
                'raw_text_length': len(full_text)
            }
        except Exception as e:
            logger.error(f"Error procesando sílabo: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def save_curso_to_db(self, db: Session, syllabus_info: Dict, drive_file_id: str) -> Optional[int]:
        try:
            from backend.database import crud
            existing = crud.get_curso_by_drive_id(db, drive_file_id)

            data = {
                "nombre": syllabus_info.get('nombre', 'Curso Desconocido'),
                "codigo": syllabus_info.get('codigo'),
                "ciclo": int(syllabus_info.get('ciclo', 1)),
                "temas": syllabus_info.get('temas', []),
                # Deprecated: se mantienen vacíos por compatibilidad
                "entidades_clave": [],
                "competencias_tecnicas": ""
            }

            if existing:
                crud.update_curso(db, existing.id, **data)
                return existing.id
            else:
                curso = crud.create_curso(db, drive_file_id=drive_file_id, **data)
                return curso.id
        except Exception as e:
            logger.error(f"Error BD Curso: {e}", exc_info=True)
            try:
                db.rollback()
            except Exception as rollback_err:
                logger.error(f"Error en rollback: {rollback_err}")
            return None

docx_processor = DOCXProcessor()
