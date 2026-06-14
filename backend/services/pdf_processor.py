import logging
import json
import os
import asyncio
import random
import re
import unicodedata
import pdfplumber
import numpy as np
from io import BytesIO
from typing import Dict, Optional, List
from sqlalchemy.orm import Session
from google import genai
from google.genai import types
from backend.services.entity_utils import get_fast_sbert_model, limpiar_entidades

logger = logging.getLogger(__name__)

def validate_inferences(
    entidades: List[str],
    historial_cursos: List[str],
    historial_contextos: List[str] = None,
    total_historial: int = 0,
    threshold: float = 0.65
) -> List[str]:
    inferred_entities = [e for e in entidades if "(inferido)" in e.lower()]
    explicit_entities = [e for e in entidades if "(inferido)" not in e.lower()]

    if not inferred_entities:
        return entidades

    if total_historial == 0:
        logger.info("El docente es nuevo (sin historial). Se mantienen las inferencias.")
        return entidades

    if not historial_cursos and not historial_contextos:
        logger.info("Docente con historial viejo (sin cursos recientes). Eliminando inferencias.")
        return explicit_entities

    model = get_fast_sbert_model()
    if not model:
        logger.error("No se pudo cargar el modelo rápido. Manteniendo inferencias.")
        return entidades

    from sklearn.metrics.pairwise import cosine_similarity

    # Construir textos de referencia: nombre del curso + sus entidades clave
    textos_referencia = []
    if historial_contextos:
        textos_referencia.extend(historial_contextos)
    else:
        textos_referencia.extend(historial_cursos)

    if not textos_referencia:
        return explicit_entities

    historial_vecs = model.encode(textos_referencia, convert_to_numpy=True)
    if historial_vecs.ndim == 1:
        historial_vecs = historial_vecs.reshape(1, -1)

    validated_entities = list(explicit_entities)

    for inf_ent in inferred_entities:
        clean_ent = inf_ent.replace("(inferido)", "").strip()
        inf_vec = model.encode([clean_ent], convert_to_numpy=True)

        sim_matrix = cosine_similarity(inf_vec, historial_vecs)
        max_sim = float(np.max(sim_matrix))

        if max_sim >= threshold:
            logger.info(f"✅ Inferencia VALIDADA: '{clean_ent}' (Similitud max: {max_sim:.2f})")
            validated_entities.append(inf_ent)
        else:
            logger.warning(f"❌ Inferencia ELIMINADA: '{clean_ent}' (Similitud max: {max_sim:.2f})")

    return validated_entities


def prompt_directo(texto_cv: str) -> str:
    return f"""
Eres un extractor de datos de CV. Solo usas lo que está en el documento.
No infieres ni completas con conocimiento propio.

RECORRE EN ORDEN:
1. CAPACITACIONES: extrae herramientas, tecnologías y metodologías 
   técnicas con nombre propio. Descarta títulos de talleres que no 
   nombren una herramienta o tecnología específica.
2. EXPERIENCIA: extrae herramientas y tecnologías usadas en roles 
   profesionales si están declaradas explícitamente.
3. PUBLICACIONES / PROYECTOS: extrae temas técnicos si los hay.

DEFINICIÓN:
- competencias_tecnicas: todo lo que el docente sabe usar o hacer de 
  forma concreta y verificable. Son herramientas, lenguajes, plataformas, 
  frameworks y metodologías técnicas con nombre propio.
  Si no hay ninguna extraíble: ["[No declarado]"].

Si un dato no está en el documento: "[No declarado]".

Devuelve ÚNICAMENTE este JSON:
{{
  "nombre": "string",
  "email": "string",
  "grado": "string",
  "competencias_tecnicas": ["string"]
}}

CV:
{texto_cv}
"""

def prompt_entidades(texto_cv: str) -> str:
    return f"""
Lee el CV y extrae EXACTAMENTE 6 áreas de conocimiento técnico 
que el docente ha demostrado dominar por experiencia docente o profesional.

REGLA FUNDAMENTAL:
NUNCA incluyas nombres de carreras, títulos académicos, grados, 
instituciones educativas ni cargos administrativos como entidades.

UNA BUENA ENTIDAD es un área de conocimiento técnico ENSEÑABLE, 
específica y verificable en el CV. Debe diferenciar a este docente 
de otro en un sistema de matching con cursos universitarios.

CRITERIOS DE EXCLUSIÓN (aplican siempre):
- Nombres de carrera: Ingeniería de Software, Ingeniería de Sistemas, 
  Sistemas de Información, Ciencias de la Computación, Ingeniería 
  Industrial, Ingeniería Informática, etc.
- Títulos académicos: Maestría en..., Doctor en..., Bachiller en..., 
  Licenciatura en...
- Instituciones: universidades, institutos, escuelas, facultades.
- Cargos: Gerente, Jefe, Director, Analista, Consultor, etc.
- Herramientas o software específicos: representan el área de 
  conocimiento que las contiene, no el área en sí misma.

REGLA DE INFERENCIA (muy restrictiva):
Solo puedes inferir una entidad desde el título académico cuando:
1. La formación sea muy concentrada (ej. Ciencias de la Computación, 
   Matemática, Ingeniería Informática pura).
2. El conocimiento sea estructuralmente inevitable en esa disciplina 
   y requiera uso continuo (ej. Algoritmos, Estructuras de Datos).
3. El CV no tenga otra información técnica declarada.

Si no cumples las tres condiciones, NO infieras. En su lugar, 
devuelve "[No declarado]" o menos de 6 entidades.

Marca cada entidad inferida con "(inferido)" al final.

EJEMPLOS DE ENTIDADES VÁLIDAS:
- Machine Learning
- Arquitectura de Software
- Gestión de Proyectos
- Reingeniería de Procesos
- Planificación Estratégica de TI
- Analítica de Datos
- Bases de Datos Distribuidas

EJEMPLOS DE LO QUE NUNCA DEBES INCLUIR:
- Ingeniería de Software
- Ingeniería de Sistemas
- Sistemas de Información
- Maestría en Ingeniería de Software
- Doctor en Educación
- Universidad Privada Antenor Orrego
- Gerente de Sistemas
- Jefe de Computo

Devuelve ÚNICAMENTE este JSON sin prefijos ni etiquetas dentro de los valores:
{{"entidades_clave": ["string"]}}

CV:
{texto_cv}
"""

class PDFProcessor:
    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        
        try:
            self.client = genai.Client(vertexai=True, project=self.project_id, location=self.location)
            logger.info(f"genai SDK inicializado en el proyecto {self.project_id}")
        except Exception as e:
            logger.error(f"Error iniciando genai Client: {e}. Revisa credenciales o permisos.", exc_info=True)
            self.client = None

    async def llamar_flash_lite(self, texto: str) -> dict:
        if not self.client: return {}
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    wait = 5 * (2 ** (attempt - 1)) + random.uniform(0, 2)
                    logger.warning(f"⏳ [CV] Flash Lite retry {attempt+1}/{max_retries} en {wait:.1f}s...")
                    await asyncio.sleep(wait)
                start_time = time.time()
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model="gemini-3.1-flash-lite",
                        contents=prompt_directo(texto),
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.1
                        )
                    ),
                    timeout=120.0
                )
                elapsed = time.time() - start_time
                logger.info(f"⏱️ [CV] Flash Lite tardó: {elapsed:.2f} segundos")
                try:
                    return json.loads(response.text.strip())
                except Exception as e:
                    logger.error(f"Error parseando Flash Lite: {e}", exc_info=True)
                    return {}
            except Exception as e:
                if ("429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)) and attempt < max_retries - 1:
                    continue
                logger.error(f"Error en Flash Lite (intento {attempt+1}): {e}", exc_info=True)
                return {}

    async def llamar_pro(self, texto: str) -> dict:
        if not self.client: return {"entidades_clave": []}
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    wait = 5 * (2 ** (attempt - 1)) + random.uniform(0, 2)
                    logger.warning(f"⏳ [CV] Gemini Pro retry {attempt+1}/{max_retries} en {wait:.1f}s...")
                    await asyncio.sleep(wait)
                start_time = time.time()
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model="gemini-2.5-pro",
                        contents=prompt_entidades(texto),
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.1
                        )
                    ),
                    timeout=120.0
                )
                elapsed = time.time() - start_time
                logger.info(f"⏱️ [CV] Gemini 2.5 Pro tardó: {elapsed:.2f} segundos")
                try:
                    return json.loads(response.text.strip())
                except Exception as e:
                    logger.error(f"Error parseando Pro: {e}", exc_info=True)
                    return {"entidades_clave": []}
            except Exception as e:
                if ("429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)) and attempt < max_retries - 1:
                    continue
                logger.error(f"Error en Gemini Pro (intento {attempt+1}): {e}", exc_info=True)
                return {"entidades_clave": []}

    async def procesar_cv(self, texto_cv: str) -> dict:
        resultado_directo, resultado_entidades = await asyncio.gather(
            self.llamar_flash_lite(texto_cv),
            self.llamar_pro(texto_cv)
        )
        if resultado_directo:
            resultado_directo["entidades_clave"] = resultado_entidades.get("entidades_clave", [])
            return resultado_directo
        return {}

    def extract_text_from_pdf(self, pdf_content: bytes) -> str:
        text = ""
        try:
            with pdfplumber.open(BytesIO(pdf_content)) as pdf:
                for page in pdf.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\\n"
        except Exception as e:
            logger.error(f"Error leyendo PDF con pdfplumber: {e}", exc_info=True)
        return text

    def extract_cv_info(self, pdf_content: bytes, filename: str = "") -> Dict:
        try:
            logger.info(f"Extracting text locally from {filename}...")
            full_text = self.extract_text_from_pdf(pdf_content)
            
            if not full_text.strip():
                logger.error(f"No se pudo extraer texto de {filename}")
                return {'success': False, 'error': 'PDF vacío o ilegible'}

            logger.info(f"Corriendo Orquestador Paralelo para CV: {filename}")
            
            ai_data = run_async(self.procesar_cv(full_text))

            if not ai_data:
                return {'success': False, 'error': 'Fallo en extracción IA'}

            comp_tec = ai_data.get('competencias_tecnicas', [])
            if isinstance(comp_tec, list):
                comp_tec = ", ".join(comp_tec)
            
            nombre = ai_data.get('nombre')
            if not nombre and filename:
                nombre = filename.replace('.pdf', '').replace('_', ' ')

            target_text = comp_tec
            
            return {
                'success': True,
                'nombre': nombre,
                'email': ai_data.get('email'),
                'grado': ai_data.get('grado'),
                'entidades_clave': ai_data.get('entidades_clave', []),
                'competencias_tecnicas': target_text,
                'raw_text': full_text,
                'raw_text_length': len(full_text)
            }
        except Exception as e:
            logger.error(f"❌ Error procesando {filename}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def save_docente_to_db(self, db: Session, cv_info: Dict, drive_file_id: str) -> Optional[int]:
        try:
            from backend.database import crud
            existing = crud.get_docente_by_drive_id(db, drive_file_id)
            
            entidades_extraidas = cv_info.get('entidades_clave', [])
            raw_text = cv_info.get('raw_text', '')
            
            # --- Limpieza de entidades: carreras, títulos, instituciones, cargos ---
            entidades_limpias = limpiar_entidades(entidades_extraidas, raw_text)
            logger.info(f"Entidades extraídas: {entidades_extraidas}")
            logger.info(f"Entidades después de limpieza: {entidades_limpias}")
            
            # --- Flujo de Purga (Validador de Inferencias) ---
            historial_cursos = []
            nombre_target = cv_info.get('nombre', 'Docente Desconocido')
            
            def normalize_name(s):
                s = unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode('utf-8')
                s = re.sub(r'[^A-Z0-9 ]', ' ', s.upper())
                return s.split()

            def match_score(nombre_hist, nombre_bd):
                words_a = normalize_name(nombre_hist)
                words_b = normalize_name(nombre_bd)
                shorter, longer = (words_a, words_b) if len(words_a) <= len(words_b) else (words_b, words_a)
                matches = sum(1 for w in shorter if w in longer)
                return matches / len(shorter) if shorter else 0

            all_hist = crud.get_all_historiales(db)
            historiales_docente = [h for h in all_hist if match_score(h.nombre_docente, nombre_target) >= 0.8]
            
            all_periods = sorted(list(set(h.ultima_vez for h in historiales_docente)), reverse=True)
            valid_periods = set(all_periods[:4]) # Máximo 4 periodos recientes DEL DOCENTE
            
            for h in historiales_docente:
                if h.ultima_vez in valid_periods:
                    historial_cursos.append(h.nombre_curso)

            historial_cursos = list(set(historial_cursos))

            # Enriquecer el historial con las entidades de cada curso dictado,
            # para no comparar la inferencia solo contra el nombre del curso.
            historial_contextos = []
            try:
                all_cursos = crud.get_all_cursos(db)
                for nombre_curso in historial_cursos:
                    best_match = None
                    best_score = 0.0
                    for curso in all_cursos:
                        score = match_score(curso.nombre, nombre_curso)
                        if score > best_score:
                            best_score = score
                            best_match = curso
                    if best_match and best_score >= 0.6:
                        entidades_curso = best_match.entidades_clave or []
                        contexto = f"{best_match.nombre}: " + ", ".join(entidades_curso)
                        historial_contextos.append(contexto)
            except Exception as e:
                logger.warning(f"No se pudieron cargar contextos de cursos para validación: {e}")

            entidades_validadas = validate_inferences(
                entidades=entidades_limpias,
                historial_cursos=historial_cursos,
                historial_contextos=historial_contextos,
                total_historial=len(historiales_docente),
                threshold=0.65
            )
            
            data = {
                "nombre": cv_info.get('nombre', 'Docente Desconocido'),
                "email": cv_info.get('email'),
                "grado": cv_info.get('grado'),
                "entidades_clave": entidades_validadas,
                "competencias_tecnicas": cv_info.get('competencias_tecnicas', '')
            }

            if existing:
                crud.update_docente(db, existing.id, **data)
                return existing.id
            else:
                doc = crud.create_docente(db, drive_file_id=drive_file_id, **data)
                return doc.id
        except Exception as e:
            logger.error(f"Error BD Docente: {e}", exc_info=True)
            try:
                db.rollback()
            except Exception as rollback_err:
                logger.error(f"Error en rollback: {rollback_err}")
            return None

pdf_processor = PDFProcessor()
