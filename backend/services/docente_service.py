"""
Servicio de orquestación para extracción y persistencia de docentes.

Encapsula el flujo: PDF → texto → LLM → validación de inferencias → perfil técnico → DB.
"""

import logging
import re
import unicodedata
from io import BytesIO
from typing import List, Mapping, Optional

import pdfplumber
from sqlalchemy.orm import Session

from backend.domain.technical_terms import TechnicalTermNormalizer
from backend.domain.validators.inference_validator import obtener_periodos_validos
from backend.llm.client import GeminiClient
from backend.llm.prompts.cv import prompt_cv_unificado, prompt_validacion_inferencias
from backend.repositories.docente_repo import DocenteRepository
from backend.repositories.historial_repo import HistorialRepository
from backend.services.entity_utils import run_async
from backend.taxonomy.catalog import get_canonical_label_lookup

logger = logging.getLogger(__name__)


class DocenteService:
  """Orquesta la extracción, validación y persistencia de un CV de docente."""

  def __init__(
    self,
    db: Session,
    llm_client: Optional[GeminiClient] = None,
    canonical_lookup: Optional[Mapping[str, str]] = None,
  ):
    self.db = db
    self.llm_client = llm_client or GeminiClient()

    self.docente_repo = DocenteRepository(db)
    self.historial_repo = HistorialRepository(db)
    self.canonical_lookup = (
      canonical_lookup
      if canonical_lookup is not None
      else get_canonical_label_lookup()
    )

  @staticmethod
  def extract_text_from_pdf(pdf_content: bytes) -> str:
    """Extrae texto plano de un PDF usando pdfplumber y aplica filtro de privacidad."""
    text = ""
    try:
      with pdfplumber.open(BytesIO(pdf_content)) as pdf:
        for page in pdf.pages:
          extracted = page.extract_text()
          if extracted:
            text += extracted + "\n"

      text = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', ' ', text)
      text = re.sub(r'(?<!\d)(?:\+?51[\s-]?)?(?:9\d{2}[\s-]?\d{3}[\s-]?\d{3})(?!\d)', ' ', text)

    except Exception as e:
      logger.error(f"Error leyendo PDF con pdfplumber: {e}", exc_info=True)
    return text

  def _normalize_name(self, s: str) -> List[str]:
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("utf-8")
    s = re.sub(r"[^A-Z0-9 ]", " ", s.upper())
    return s.split()

  def _match_score(self, nombre_a: str, nombre_b: str) -> float:
    words_a = self._normalize_name(nombre_a)
    words_b = self._normalize_name(nombre_b)
    shorter, longer = (words_a, words_b) if len(words_a) <= len(words_b) else (words_b, words_a)
    matches = sum(1 for w in shorter if w in longer)
    return matches / len(shorter) if shorter else 0.0

  def _load_historial_for(self, nombre_docente: str) -> List[str]:
    """Devuelve nombres de cursos del historial reciente del docente."""
    all_hist = self.historial_repo.get_all()
    historiales_docente = [
      h for h in all_hist if self._match_score(h.nombre_docente, nombre_docente) >= 0.8
    ]

    valid_periods = obtener_periodos_validos()
    historiales_validos = [h for h in historiales_docente if h.ultima_vez in valid_periods]

    return list({h.nombre_curso for h in historiales_validos})

  def _validate_inferences(
    self,
    menciones_conceptuales: List[dict],
    nombre_docente: str,
  ) -> List[dict]:
    """Filtra menciones conceptuales usando LLM as a Judge contra historial reciente."""
    if not menciones_conceptuales:
      return []

    inferidas = [
      mencion for mencion in menciones_conceptuales
      if not mencion.get("explicito")
    ]
    if not inferidas:
      return menciones_conceptuales

    historial_cursos = self._load_historial_for(nombre_docente)
    if not historial_cursos:
      logger.info(
        "Sin historial reciente que respalde inferencias. "
        "Se conservan los dominios explícitos y se descartan sólo los inferidos."
      )
      return [
        mencion for mencion in menciones_conceptuales
        if mencion.get("explicito")
      ]

    terminos_inferidos = [m["termino"] for m in inferidas if m.get("termino")]

    cursos_str = "\n".join(f"- {c}" for c in historial_cursos)
    inferencias_str = "\n".join(f"- {h}" for h in terminos_inferidos)

    prompt = prompt_validacion_inferencias(cursos_str, inferencias_str)

    validadas_json = run_async(
        self.llm_client.generate_flash_lite_json(prompt, label="CV-Validacion")
    )

    if not validadas_json:
        logger.warning("Fallo la validacion LLM, descartando inferencias.")
        return [m for m in menciones_conceptuales if m.get("explicito")]

    validadas_norm = set()
    for v in validadas_json:
        if isinstance(v, dict) and v.get("es_valida"):
            validadas_norm.add(str(v.get("habilidad", "")).strip().lower())

    resultado = []
    for m in menciones_conceptuales:
        if m.get("explicito"):
            resultado.append(m)
        elif m.get("termino", "").strip().lower() in validadas_norm:
            resultado.append(m)

    return resultado

  def _construir_perfil_tecnico(self, menciones_completas: list) -> list:
    """Construye el perfil procesado; descarta pares bilingües inválidos."""
    resultado = TechnicalTermNormalizer.normalize_many(
      menciones_completas,
      canonical_lookup=self.canonical_lookup,
    )
    if resultado.rejected:
      resumen = ", ".join(
        f"{item.term or '<vacío>'}:{item.reason}"
        for item in resultado.rejected[:10]
      )
      logger.warning(
        "Se descartaron %s términos técnicos inválidos antes de persistir: %s",
        len(resultado.rejected),
        resumen,
      )
    return resultado.profile

  def extract_and_save(
    self,
    pdf_content: bytes,
    drive_file_id: str,
    filename: str = "",
    propietario_email: str = "legacy@upao.edu.pe",
  ) -> Optional[int]:
    """Extracción de un CV, validación y persistencia del perfil técnico en la DB."""
    try:
      full_text = self.extract_text_from_pdf(pdf_content)
      if not full_text.strip():
        logger.error(f"PDF vacío o ilegible: {filename}")
        return None

      logger.info(f"Extrayendo CV con LLM unificado: {filename}")

      resultado_directo = run_async(
        self.llm_client.generate_flash_lite_json(
          prompt_cv_unificado(full_text), label="CV-unificado"
        )
      )

      if not isinstance(resultado_directo, dict) or not resultado_directo:
        logger.error(f"Fallo en extracción IA de CV: {filename}")
        return None

      nombre = resultado_directo.get("nombre") or filename.replace(".pdf", "").replace("_", " ")
      if nombre:
        nombre = nombre.strip().title()

      herramientas_raw = resultado_directo.get("herramientas_tecnologicas", [])
      menciones = [
        item for item in herramientas_raw
        if isinstance(item, dict)
      ] if isinstance(herramientas_raw, list) else []
      for m in menciones:
        m["explicito"] = True

      dominios_raw = resultado_directo.get("dominios_conceptuales", [])
      menciones_conceptuales = [
        item for item in dominios_raw
        if isinstance(item, dict)
      ] if isinstance(dominios_raw, list) else []
      for m in menciones_conceptuales:
        m["explicito"] = bool(m.get("explicito", False))

      menciones_conceptuales = self._validate_inferences(menciones_conceptuales, nombre)

      todas_las_menciones = menciones + menciones_conceptuales
      perfil_tecnico = self._construir_perfil_tecnico(todas_las_menciones)
      if not perfil_tecnico:
        logger.error(
          "La extracción no produjo términos bilingües válidos; no se sobrescribe el perfil: %s",
          filename,
        )
        return None

      docente = self.docente_repo.get_or_create(
        drive_file_id=drive_file_id,
        nombre=nombre,
        grado=resultado_directo.get("grado"),
        propietario_email=propietario_email,
      )
      self.docente_repo.update_profile(
        docente_id=docente.id,
        perfil_tecnico=perfil_tecnico,
      )

      self.db.commit()
      logger.info(f"Docente guardado (Perfil Tecnico listo): id={docente.id}, nombre={nombre}")
      return docente.id

    except Exception as e:
      logger.error(f"Error en DocenteService.extract_and_save: {e}", exc_info=True)
      try:
        self.db.rollback()
      except Exception as rollback_err:
        logger.error(f"Error en rollback: {rollback_err}")
      return None
