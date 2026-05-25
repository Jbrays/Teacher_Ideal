import logging
import json
import os
import time
import vertexai
from pathlib import Path
from typing import Dict, Optional
from docx import Document
from io import BytesIO
from vertexai.generative_models import GenerativeModel
from sqlalchemy.orm import Session

# Configuración de logger
logger = logging.getLogger(__name__)

# Se eliminó la importación de ner_service por la arquitectura de LLM Unificado

class DOCXProcessor:
    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-3.1-flash-lite")

        try:
            vertexai.init(project=self.project_id, location=self.location)
            self.model = GenerativeModel(self.model_name)
            logger.info(f"Vertex AI (DOCX) inicializado en el proyecto {self.project_id}")
        except Exception as e:
            logger.error(f"Error iniciando Vertex AI en DOCXProcessor: {e}")
            self.model = None

    def extract_text_from_docx(self, docx_bytes: bytes) -> str:
        """Extrae todo el texto plano del DOCX, incluyendo tablas."""
        try:
            doc = Document(BytesIO(docx_bytes))
            text = []
            
            # Extraer párrafos
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text.append(paragraph.text)
            
            # Extraer tablas (vital para el formato UPAO)
            for table in doc.tables:
                for row in table.rows:
                    row_text = []
                    for cell in row.cells:
                        if cell.text.strip():
                            row_text.append(cell.text.strip())
                    if row_text:
                        text.append(" | ".join(row_text))
            
            return "\n".join(text)
        except Exception as e:
            logger.error(f"Error leyendo DOCX crudo: {e}")
            return ""

    def _parse_with_gemini(self, raw_text: str) -> Dict:
        """
        Usa Vertex AI para entender la estructura del Sílabo UPAO.
        """
        if not self.model:
            return {}

        prompt = f"""
        Actúa como un analista académico. Tienes el texto crudo de un Sílabo universitario.
        Extrae la información clave en un JSON estricto.

        Formato requerido:
        {{
            "nombre": "string (Nombre de la asignatura)",
            "codigo": "string",
            "ciclo": 1 (entero),
            "descripcion": "string (Texto de la SUMILLA)",
            "entidades_clave": ["string", "string"],
            "perfil_sintetico": "string (Resumen denso de los temas para búsqueda vectorial)"
        }}

        Texto:
        {raw_text[:7000]}
        """

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(prompt)
                cleaned_response = response.text.replace("```json", "").replace("```", "").strip()
                return json.loads(cleaned_response)
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 5 * (attempt + 1)
                    logger.warning(f"⚠️ Error en Vertex AI ({e}). Reintentando sílabo en {wait_time}s... ({attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ Falló Vertex AI de forma definitiva para el sílabo tras {max_retries} intentos: {e}")
                    return {}
        
        return {}

    def extract_syllabus_info(self, docx_bytes: bytes, filename: str = "") -> Dict:
        try:
            # 1. Leer texto crudo
            full_text = self.extract_text_from_docx(docx_bytes)
            if not full_text:
                return {'success': False, 'error': 'DOCX vacío o ilegible'}

            # 2. Interpretar con Vertex AI
            ai_data = self._parse_with_gemini(full_text)
            
            # Corrección para listas
            if isinstance(ai_data, list):
                ai_data = ai_data[0] if ai_data else {}

            # Valores por defecto
            nombre = ai_data.get('nombre')
            if not nombre and filename:
                nombre = filename.replace('.docx', '').replace('_', ' ')

            # 3. Enriquecer con datos del JSON
            target_text = ai_data.get('perfil_sintetico', full_text)
            entities = ai_data.get('entidades_clave', [])
            
            return {
                'success': True,
                'nombre': nombre,
                'codigo': ai_data.get('codigo'),
                'ciclo': ai_data.get('ciclo', 1),
                'descripcion': ai_data.get('descripcion', ''),
                'entidades_clave': entities,
                'perfil_sintetico': target_text,
                'raw_text_length': len(full_text)
            }
        except Exception as e:
            logger.error(f"Error procesando sílabo: {e}")
            return {'success': False, 'error': str(e)}

    def save_curso_to_db(self, db: Session, syllabus_info: Dict, drive_file_id: str) -> Optional[int]:
        try:
            from backend.database import crud
            existing = crud.get_curso_by_drive_id(db, drive_file_id)
            
            data = {
                "nombre": syllabus_info.get('nombre', 'Curso Desconocido'),
                "codigo": syllabus_info.get('codigo'),
                "ciclo": int(syllabus_info.get('ciclo', 1)),
                "descripcion": syllabus_info.get('descripcion'),
                "entidades_clave": syllabus_info.get('entidades_clave', []),
                "perfil_sintetico": syllabus_info.get('perfil_sintetico', '')
            }

            if existing:
                crud.update_curso(db, existing.id, **data)
                return existing.id
            else:
                curso = crud.create_curso(db, drive_file_id=drive_file_id, **data)
                return curso.id
        except Exception as e:
            logger.error(f"Error BD Curso: {e}")
            try:
                db.rollback()
            except Exception as rollback_err:
                logger.error(f"Error en rollback: {rollback_err}")
            return None

docx_processor = DOCXProcessor()