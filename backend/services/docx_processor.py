import logging
import json
import os
import random
import re
from pathlib import Path
from typing import Dict, Optional, List
from docx import Document
from io import BytesIO
from sqlalchemy.orm import Session
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


# Filtro de seguridad post-extracción: elimina items que no son contenido temático
PALABRAS_EXCLUIR = re.compile(
    r'(?i)('
    r'evaluaci[oó]n\s*(parcial|final|de\s*proceso|sustitutoria?)?|'
    r'examen\s*(parcial|final|sustitutorio)?|'
    r'retroalimentaci[oó]n\s*(de\s*contenidos?|de\s*los\s*contenidos?|y\s*nivelaci[oó]n|de\s*contenidos\s*desarrollados?)?|'
    r'nivelaci[oó]n|recuperaci[oó]n\s+(acad[eé]mica|de\s*contenidos)|'
    r'hito\s*\d(\s*del\s*proyecto)?|'
    r'semana\s*de\s*actualizaci[oó]n|foro\s*participativo|'
    r'presentaci[oó]n\s*(final\s*del\s*proyecto|de\s*proyectos|formal\s+de\s+trabajos|y\s*revisi[oó]n\s*de\s*trabajos)|'
    r'informe\s*final|preparaci[oó]n\s*para|'
    r'presentaci[oó]n\s*del\s*(curso|s[ií]labo|programa)|'
    r'socializaci[oó]n\s*del\s*s[ií]labo|bienvenida(\s*al\s*curso)?|'
    r'clase\s*conferencia|datos\s*(personales|profesionales)\s*del\s*docente|'
    r'revisi[oó]n\s*del\s*reglamento|expectativas\s+laborales|'
    r'formaci[oó]n\s*de\s*equipos?|conformaci[oó]n\s*de\s*equipos?|'
    r'sustentaci[oó]n(\s*individual|\s*de\s*equipos?|\s*de\s*cada\s*integrante)|'
    r'continuaci[oó]n\s*de\s*sustentaciones|diagn[oó]stico\s*de\s*recursos|'
    r'accion\s*tutorial|tutor[ií]a\s+acad[eé]mica|'
    r'resultados\s*de\s*la\s*investigaci[oó]n\s*y\s*su\s*impacto|'
    r'desarrollo\s+de\s+una\s+clase\s+conferencia|'
    r'contenidos\s+trabajados\s+hasta|la\s+semana\s+\d+|los\s+casos\s+pertinentes|'
    r'observaci[oó]n\s+e\s+interrogantes|respuestas\s+a\s+preguntas|'
    r'avance\s+de\s+la\s+asignatura|avance\s+de\s+trabajo|'
    r'\(\s*[A-Z]{2,4}\s*\)\s*\d+%'
    r')'
)


# Actividades del estudiante/docente, no contenido temático
ACTIVIDADES_EXCLUIR = re.compile(
    r'(?i)('
    r'^(se\s+(desarrolla|desarrollan|revisa|revisan|presenta|presentan|conforman|'
    r'gu[ií]a|da|sustenta|discute|identifican|caracteriza|caracterizan|'
    r'elabora|elaboran|aplica|aplican|define|definen|realiza|realizan|'
    r'internaliza|internalizan|complementa|complementan|desarrolla|desarrollan))\b|'
    r'^(trabajo\s+en\s+grupo\s+para|caso\s+de\s+aplicaci[oó]n|'
    r'en\s+la\s+pr[aá]ctica|en\s+clase\s+te[oó]rica|'
    r'desarrollo\s+de\s+contenidos|se\s+revisan\s+las\s+propuestas|'
    r'aplicaci[oó]n\s+de\s+test|desarrollo\s+del\s+test|'
    r'continuaci[oó]n\s+de\s+sustentaciones|'
    r'sustentaci[oó]n\s+de\s+cada\s+integrante|'
    r'aplicaci[oó]n\s+de\s+test\s+y\s+retroalimentaci[oó]n|'
    r'revisi[oó]n\s+de\s+devops|revisi[oó]n\s+de\s+las\s+propuestas|'
    r'el\s+desarrollo\s+de\s+sistemas\s+software|'
    r'respuestas\s+a\s+preguntas|'
    r'entregado\s+en\s+plataforma\s+canvas|'
    r'trabajos\s+individuales\s+no\s+son\s+v[aá]lidos)|'
    r'objeto\s+de\s+estudio|'
    r'organizaci[oó]n\s+objeto\s+de\s+estudio|'
    r'monitoreado\s+por\s+el\s+docente|'
    r'en\s+el\s+avance\s+de\s+la\s+asignatura|'
    r'actividades\s+o\s+acciones\s+de\s+retroalimentaci[oó]n'
    r')'
)


def prompt_temas_silabo(texto_semanas: str) -> str:
    return f"""Eres un extractor de contenidos temáticos de sílabos universitarios.

Recibirás un texto con el contenido de la columna "Contenidos Temáticos" de un sílabo,
organizado semana por semana. Cada línea empieza con "Semana X:".

Tu tarea es devolver una lista limpia de temas. Reglas:
1. Extrae SOLO contenido temático real.
2. Omite semanas de evaluación, retroalimentación, presentación de proyectos, hitos, foros y socialización del sílabo.
3. Cada tema debe ser una frase con sentido completo. No devuelvas palabras sueltas.
4. Si una semana tiene varios subtemas, divídelos en items separados.
5. Si un subtema es muy corto o genérico por sí solo, combínalo con el tema al que pertenece para que tenga sentido.
6. No inventes temas que no estén en el texto.
7. No dupliques temas.
8. Devuelve SOLO este JSON: {{"nombre": "...", "codigo": "...", "ciclo": ..., "temas": ["..."]}}

TEXTO:
{texto_semanas}
"""


def _normalizar_texto(texto: str) -> str:
    """Limpia espacios, saltos de línea y puntuación redundante."""
    t = texto.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    t = re.sub(r'\s+', ' ', t).strip()
    t = re.sub(r'\s+([.,;:!?])', r'\1', t)
    return t


def _es_valido(tema: str) -> bool:
    """Filtro rápido de seguridad para temas devueltos por Gemini."""
    if not tema or not tema.strip():
        return False
    t = _normalizar_texto(tema)
    if PALABRAS_EXCLUIR.search(t):
        return False
    if ACTIVIDADES_EXCLUIR.search(t):
        return False
    return True


def _limpiar_temas(temas: List[str]) -> List[str]:
    """Elimina duplicados, vacíos y items filtrados."""
    if not temas:
        return []
    vistos = set()
    limpios = []
    for t in temas:
        t = _normalizar_texto(t)
        if not t:
            continue
        if not _es_valido(t):
            logger.info(f"Tema excluido post-Gemini: '{t[:80]}...'")
            continue
        clave = re.sub(r'[^a-z0-9áéíóúñ]+', '', t.lower())
        if clave in vistos:
            continue
        vistos.add(clave)
        limpios.append(t)
    return limpios


def _detectar_columnas_tabla(fila_encabezado: List[str]) -> tuple:
    """Detecta los índices de semana y contenido temático en una fila de encabezado."""
    idx_semana = None
    idx_contenido = None
    for i, cell_text in enumerate(fila_encabezado):
        txt_lower = cell_text.lower()
        if any(p in txt_lower for p in ['semana', 'n° semanas', 'n semanas', 'semanas']):
            idx_semana = i
        if any(p in txt_lower for p in ['contenidos temáticos', 'contenido temático', 'contenidos', 'contenido tematico']):
            idx_contenido = i
    return idx_semana, idx_contenido


def _extraer_texto_semanal(docx_bytes: bytes) -> tuple:
    """
    Extrae el contenido de la tabla de programación semanal y lo devuelve como:
    - texto formateado para Gemini
    - cantidad de semanas con contenido real
    """
    try:
        doc = Document(BytesIO(docx_bytes))
    except Exception as e:
        logger.error(f"Error abriendo DOCX: {e}")
        return "", 0

    semanas = []
    idx_semana_global = None
    idx_contenido_global = None
    ultima_semana = None
    visto = set()

    for table in doc.tables:
        rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
        if not rows:
            continue

        idx_semana, idx_contenido = _detectar_columnas_tabla(rows[0])
        if idx_contenido is not None:
            idx_semana_global = idx_semana if idx_semana is not None else 0
            idx_contenido_global = idx_contenido
            data_rows = rows[1:]
        elif idx_contenido_global is not None:
            idx_semana = idx_semana_global
            idx_contenido = idx_contenido_global
            data_rows = rows
        else:
            if len(rows[0]) >= 2:
                idx_semana = 0
                idx_contenido = 1
                data_rows = rows
            else:
                continue

        for cells in data_rows:
            if idx_contenido >= len(cells):
                continue
            texto_semana = cells[idx_semana].strip() if idx_semana is not None and idx_semana < len(cells) else ""
            texto_contenido = cells[idx_contenido].strip()
            if not texto_contenido:
                continue

            match = re.search(r'semana\s*(\d+)', texto_semana, re.IGNORECASE)
            if match:
                ultima_semana = int(match.group(1))
            elif ultima_semana is None:
                continue

            clave = (ultima_semana, texto_contenido.lower())
            if clave in visto:
                continue
            visto.add(clave)
            semanas.append((ultima_semana, _normalizar_texto(texto_contenido)))

    if not semanas:
        return "", 0

    lineas = [f"Semana {num}: {contenido}" for num, contenido in semanas]
    return "\n".join(lineas), len(semanas)


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

    def llamar_flash_lite(self, texto: str) -> dict:
        if not self.client:
            return {}
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    wait = 5 * (2 ** (attempt - 1)) + random.uniform(0, 2)
                    logger.warning(f"⏳ [Sílabo] Flash Lite retry {attempt+1}/{max_retries} en {wait:.1f}s...")
                    time.sleep(wait)
                start_time = time.time()
                response = self.client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=prompt_temas_silabo(texto),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1
                    )
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

    def procesar_silabo(self, texto_semanas: str) -> dict:
        return self.llamar_flash_lite(texto_semanas)

    def extract_text_from_docx(self, docx_bytes: bytes) -> str:
        """Extrae todo el texto plano del DOCX, incluyendo tablas, respetando el orden real."""
        try:
            from docx.oxml.ns import qn
            doc = Document(BytesIO(docx_bytes))
            text = []

            for block in doc.element.body:
                if block.tag == qn('w:p'):
                    from docx.text.paragraph import Paragraph
                    p = Paragraph(block, doc)
                    if p.text.strip():
                        text.append(p.text)
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

    def _extraer_metadata_desde_filename(self, filename: str) -> Dict:
        """Extrae nombre y código aproximados desde el nombre del archivo."""
        base = filename.replace('.docx', '').replace('_', ' ').strip()
        match = re.search(r'\b([A-Z]{2,6}-\d{3,4})\b', base)
        codigo = match.group(1) if match else None
        nombre = base
        if codigo:
            partes = base.split(codigo)
            if len(partes) > 1:
                nombre = partes[-1].strip(' -')
        return {'nombre': nombre, 'codigo': codigo}

    def extract_syllabus_info(self, docx_bytes: bytes, filename: str = "") -> Dict:
        try:
            # 1. Extraer texto semanal determinísticamente
            texto_semanas, num_semanas = _extraer_texto_semanal(docx_bytes)
            if not texto_semanas:
                return {'success': False, 'error': 'No se encontró tabla de programación semanal'}

            logger.info(f"Extrayendo temas del sílabo: {filename} ({num_semanas} semanas detectadas)")

            # 2. Enviar a Gemini Flash Lite
            ai_data = self.procesar_silabo(texto_semanas)

            if not ai_data:
                return {'success': False, 'error': 'Fallo en extracción IA'}

            temas_extraidos = ai_data.get('temas', [])
            temas_limpios = _limpiar_temas(temas_extraidos)

            logger.info(f"Temas extraídos: {len(temas_extraidos)} | Temas válidos: {len(temas_limpios)}")

            # 3. Validación: al menos 1 tema por semana detectada
            if len(temas_limpios) < num_semanas:
                logger.warning(f"Gemini devolvió menos temas ({len(temas_limpios)}) que semanas detectadas ({num_semanas})")

            # 4. Metadata
            metadata_filename = self._extraer_metadata_desde_filename(filename) if filename else {}
            nombre = ai_data.get('nombre') or metadata_filename.get('nombre')
            codigo = ai_data.get('codigo') or metadata_filename.get('codigo')
            ciclo = ai_data.get('ciclo', 1)

            if not nombre and filename:
                nombre = filename.replace('.docx', '').replace('_', ' ')

            return {
                'success': True,
                'nombre': nombre,
                'codigo': codigo,
                'ciclo': ciclo,
                'temas': temas_limpios,
                'raw_text': self.extract_text_from_docx(docx_bytes),
                'raw_text_length': len(self.extract_text_from_docx(docx_bytes))
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
                "temas": syllabus_info.get('temas', [])
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
