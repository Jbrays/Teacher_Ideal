import logging
import json
import os
import asyncio
import random
from pathlib import Path
from typing import Dict, Optional
from docx import Document
from io import BytesIO
from sqlalchemy.orm import Session
from google import genai
from google.genai import types
from backend.services.entity_utils import limpiar_entidades, run_async

logger = logging.getLogger(__name__)

def prompt_directo_silabo(texto_silabo: str) -> str:
    return f"""
Eres un extractor de información estricto. Solo usas lo que está 
literalmente en el documento. No puedes inferir ni completar.

RECORRE EN ORDEN:
1. ENCABEZADO: extrae nombre del curso, código y ciclo.
2. UNIDADES Y SEMANAS: recorre CADA unidad y CADA semana sin excepción.
   Por cada semana extrae todo lo mencionado en Contenidos Temáticos 
   y Actividades de Aprendizaje que sea conocimiento técnico enseñable 
   con nombre propio.
3. CONSOLIDA sin duplicados.

DEFINICIÓN:
- competencias_tecnicas: lista exhaustiva de todo lo encontrado en 
  el paso 2. Son herramientas, lenguajes, frameworks, metodologías, 
  teorías y paradigmas con nombre propio declarados explícitamente 
  en el documento.
  Si no hay nada explícito: ["[No declarado]"].

Si un dato no está en el documento: "[No declarado]".
Los valores del JSON no deben contener prefijos ni etiquetas.
Incorrecto: "Competencias Técnicas: Big Data"
Correcto: "Big Data"

Devuelve ÚNICAMENTE este JSON:
{{
  "nombre": "string",
  "codigo": "string",
  "ciclo": 0,
  "competencias_tecnicas": ["string"]
}}

DOCUMENTO COMPLETO:
{texto_silabo}
"""

# LLAMADA 2 — Gemini 2.5 Pro — entidades clave
def prompt_entidades_silabo(texto_silabo: str) -> str:
    return f"""
Lee el sílabo completo y determina EXACTAMENTE 6 áreas de conocimiento 
técnico que un docente debe dominar para dictar este curso.

REGLA FUNDAMENTAL:
NUNCA incluyas el nombre del curso, nombres de carreras, títulos 
académicos, instituciones, cargos administrativos ni elementos de 
acreditación como entidades.

UNA BUENA ENTIDAD representa conocimiento técnico enseñable, 
específico y verificable en el sílabo. Debe diferenciar este curso 
de otros en un sistema de matching con docentes.

CRITERIOS DE EXCLUSIÓN (aplican siempre):
- Nombre del curso o palabras clave del título del curso.
- Nombres de carrera: Ingeniería de Software, Ingeniería de Sistemas, 
  Sistemas de Información, Ciencias de la Computación, etc.
- Títulos académicos: Maestría en..., Doctor en..., etc.
- Instituciones: universidades, facultades, escuelas.
- Cargos: Gerente, Jefe, Director, etc.
- Elementos administrativos o de acreditación.
- Títulos de unidad que funcionan como agrupadores temáticos. La 
  entidad debe ser el conocimiento técnico dentro de la unidad.
- Herramientas o software específicos: representan el área de 
  conocimiento que las contiene, no el área en sí misma.

CRITERIO DE SELECCIÓN:
Basa tu selección en los Contenidos Temáticos por semana y las 
actividades prácticas calificadas. No en la sumilla sola ni en el 
nombre del curso.
Si un tema aparece en múltiples semanas, cuenta como una sola 
entidad más relevante, no como varias.

EJEMPLOS DE ENTIDADES VÁLIDAS:
- Arquitectura de Software
- Gestión de Requerimientos
- Pruebas y Validación de Software
- Desarrollo de APIs
- Bases de Datos Distribuidas
- Metodologías Ágiles

EJEMPLOS DE LO QUE NUNCA DEBES INCLUIR:
- Sistemas de Información Transaccionales
- Ingeniería de Software
- Universidad Privada Antenor Orrego
- Facultad de Ingeniería
- Unidad 1: Introducción
- Acreditación

Devuelve ÚNICAMENTE este JSON sin prefijos ni etiquetas dentro de los valores:
{{"entidades_clave": ["string"]}}

DOCUMENTO COMPLETO:
{texto_silabo}
"""

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
                        contents=prompt_directo_silabo(texto),
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

    async def llamar_pro(self, texto: str) -> dict:
        if not self.client: return {"entidades_clave": []}
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    wait = 5 * (2 ** (attempt - 1)) + random.uniform(0, 2)
                    logger.warning(f"⏳ [Sílabo] Gemini Pro retry {attempt+1}/{max_retries} en {wait:.1f}s...")
                    await asyncio.sleep(wait)
                start_time = time.time()
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model="gemini-2.5-pro",
                        contents=prompt_entidades_silabo(texto),
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.1
                        )
                    ),
                    timeout=120.0
                )
                elapsed = time.time() - start_time
                logger.info(f"⏱️ [Sílabo] Gemini 2.5 Pro tardó: {elapsed:.2f} segundos")
                try:
                    return json.loads(response.text.strip())
                except Exception as e:
                    logger.error(f"Error parseando Pro (DOCX): {e}")
                    return {"entidades_clave": []}
            except Exception as e:
                if ("429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)) and attempt < max_retries - 1:
                    continue
                logger.error(f"Error en Gemini Pro Sílabo (intento {attempt+1}): {e}", exc_info=True)
                return {"entidades_clave": []}

    async def procesar_silabo(self, texto_silabo: str) -> dict:
        resultado_directo, resultado_entidades = await asyncio.gather(
            self.llamar_flash_lite(texto_silabo),
            self.llamar_pro(texto_silabo)
        )
        if resultado_directo:
            resultado_directo["entidades_clave"] = resultado_entidades.get("entidades_clave", [])
            return resultado_directo
        return {}

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

            logger.info(f"Corriendo Orquestador Paralelo para Sílabo: {filename}")
            
            # 2. Orquestar modelos
            ai_data = run_async(self.procesar_silabo(full_text))

            if not ai_data:
                return {'success': False, 'error': 'Fallo en extracción IA'}

            # Valores por defecto
            nombre = ai_data.get('nombre')
            if not nombre and filename:
                nombre = filename.replace('.docx', '').replace('_', ' ')

            # 3. Enriquecer con datos del JSON
            comp_tec = ai_data.get('competencias_tecnicas', [])
            if isinstance(comp_tec, list):
                comp_tec = ", ".join(comp_tec)
            target_text = comp_tec
            entities = ai_data.get('entidades_clave', [])
            
            return {
                'success': True,
                'nombre': nombre,
                'codigo': ai_data.get('codigo'),
                'ciclo': ai_data.get('ciclo', 1),
                'entidades_clave': entities,
                'competencias_tecnicas': target_text,
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

            entidades_extraidas = syllabus_info.get('entidades_clave', [])
            raw_text = syllabus_info.get('raw_text', '')

            entidades_limpias = limpiar_entidades(
                entidades_extraidas,
                raw_text,
                min_entidades=3,
                max_entidades=6
            )
            logger.info(f"Entidades de sílabo extraídas: {entidades_extraidas}")
            logger.info(f"Entidades de sílabo después de limpieza: {entidades_limpias}")

            data = {
                "nombre": syllabus_info.get('nombre', 'Curso Desconocido'),
                "codigo": syllabus_info.get('codigo'),
                "ciclo": int(syllabus_info.get('ciclo', 1)),
                "entidades_clave": entidades_limpias,
                "competencias_tecnicas": syllabus_info.get('competencias_tecnicas', '')
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