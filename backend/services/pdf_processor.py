import logging
import json
import os
import vertexai
from pathlib import Path
from vertexai.generative_models import GenerativeModel, Part
from typing import Dict, Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Se eliminó la importación de ner_service por la arquitectura de LLM Unificado

class PDFProcessor:
    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-3.1-flash-lite")

        try:
            # En Cloud Run o App Engine usa las credenciales por defecto de la aplicación (ADC)
            # En local, usa GOOGLE_APPLICATION_CREDENTIALS si está en el archivo .env o sistema
            vertexai.init(project=self.project_id, location=self.location)
            self.model = GenerativeModel(self.model_name)
            logger.info(f"Vertex AI inicializado en el proyecto {self.project_id}")
        except Exception as e:
            logger.error(f"Error iniciando Vertex AI: {e}. Revisa credenciales o permisos.")
            self.model = None

    def _process_with_multimodality(self, pdf_content: bytes, filename: str) -> Dict:
        if not self.model:
            return {}

        try:
            pdf_part = Part.from_data(
                mime_type="application/pdf",
                data=pdf_content
            )
        except Exception as e:
            logger.error(f"Error creando Part para {filename}: {e}")
            return {}

        prompt = """
        Analiza este PDF (Curriculum Vitae) y devuelve un JSON estricto con el siguiente formato.
        IMPORTANTE: 
        - 'nombre' debe ser EXCLUSIVAMENTE el nombre completo de la persona (el profesor o candidato). NUNCA extraigas nombres de universidades, empresas o instituciones en este campo.
        - En lugar de un resumen libre, extrae la información en las categorías fijas indicadas abajo.
        - Si no encuentras información para alguna de las categorías de texto, DEBES escribir exactamente la cadena "[Información No Declarada]". No lo dejes vacío ni inventes datos.
        - 'entidades_clave' debe ser una lista de strings con tecnologías, metodologías o áreas de conocimiento detectadas.
        {
            "nombre": "string",
            "email": "string",
            "grado": "string",
            "competencias_tecnicas": "string o [Información No Declarada]",
            "experiencia_docente": "string o [Información No Declarada]",
            "formacion_academica": "string o [Información No Declarada]",
            "entidades_clave": ["string", "string"]
        }
        """

        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(
                    [pdf_part, prompt],
                    generation_config={
                        "response_mime_type": "application/json",
                        "temperature": 0.1,
                        "max_output_tokens": 8192  # Increased to prevent truncation
                    }
                )
                
                cleaned_text = response.text.replace("```json", "").replace("```", "").strip()
                return json.loads(cleaned_text)
                
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 5 * (attempt + 1)
                    logger.warning(f"⚠️ Error en Vertex AI ({e}). Reintentando en {wait_time}s... ({attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ Falló Vertex AI definitivamente tras {max_retries} intentos para {filename}: {e}")
                    return {}

    def extract_cv_info(self, pdf_content: bytes, filename: str = "") -> Dict:
        try:
            ai_data = self._process_with_multimodality(pdf_content, filename)

            # Corrección: Si la IA devuelve una lista [{}], tomamos el primer elemento
            if isinstance(ai_data, list):
                if len(ai_data) > 0:
                    ai_data = ai_data[0]
                else:
                    ai_data = {}

            if not ai_data:
                return {
                    "success": False,
                    "error": "Fallo en análisis IA",
                    "filename": filename
                }

            name = ai_data.get("nombre")
            email = ai_data.get("email")
            grado = ai_data.get("grado") or "No especificado"

            if not name and filename:
                name = filename.replace(".pdf", "").replace("_", " ").strip().title()

            comp_tec = ai_data.get("competencias_tecnicas", "[Información No Declarada]")
            exp_doc = ai_data.get("experiencia_docente", "[Información No Declarada]")
            form_acad = ai_data.get("formacion_academica", "[Información No Declarada]")
            
            final_text = f"Competencias Técnicas: {comp_tec}. Experiencia Docente: {exp_doc}. Formación Académica: {form_acad}."
            entities = ai_data.get("entidades_clave", [])

            return {
                "success": True,
                "filename": filename,
                "name": name,
                "email": email,
                "grado": grado,
                "entidades_clave": entities,
                "perfil_sintetico": final_text
            }

        except Exception as e:
            logger.error(f"Error procesando {filename}: {e}")
            return {"success": False, "error": str(e), "filename": filename}

    def save_docente_to_db(self, db: Session, cv_info: Dict, drive_file_id: str) -> Optional[int]:
        try:
            from backend.database import crud
            
            existing = crud.get_docente_by_drive_id(db, drive_file_id)

            datos_docente = {
                "nombre": cv_info.get("name"),
                "email": cv_info.get("email"),
                "grado": cv_info.get("grado"),
                "entidades_clave": cv_info.get("entidades_clave", []),
                "perfil_sintetico": cv_info.get("perfil_sintetico", "")
            }

            if existing:
                crud.update_docente(db, existing.id, **datos_docente)
                logger.info(f"Docente actualizado: {datos_docente['nombre']}")
                return existing.id
            else:
                docente = crud.create_docente(db, drive_file_id=drive_file_id, **datos_docente)
                logger.info(f"Nuevo docente creado: {datos_docente['nombre']}")
                return docente.id
                
        except Exception as e:
            logger.error(f"Error guardando docente en BD: {e}")
            try:
                db.rollback()
            except Exception as rollback_err:
                logger.error(f"Error en rollback: {rollback_err}")
            return None

pdf_processor = PDFProcessor()
