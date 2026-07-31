"""
Servicio de orquestación para extracción y persistencia de cursos.

Encapsula el flujo: DOCX → texto → LLM → perfil técnico → persistencia en DB.
"""

import logging
from io import BytesIO
from typing import Any, Dict, List, Mapping, Optional

from docx import Document
from docx.oxml.ns import qn
from sqlalchemy.orm import Session

from backend.domain.technical_terms import TechnicalTermNormalizer
from backend.llm.client import GeminiClient
from backend.llm.prompts.syllabus import prompt_directo_silabo
from backend.repositories.curso_repo import CursoRepository
from backend.services.entity_utils import run_async
from backend.taxonomy.catalog import get_canonical_label_lookup

logger = logging.getLogger(__name__)


class CursoService:
  """Orquesta la extracción y persistencia de un sílabo de curso."""

  def __init__(
    self,
    db: Session,
    llm_client: Optional[GeminiClient] = None,
    canonical_lookup: Optional[Mapping[str, str]] = None,
  ):
    self.db = db
    self.llm_client = llm_client or GeminiClient()
    self.curso_repo = CursoRepository(db)
    self.canonical_lookup = (
      canonical_lookup
      if canonical_lookup is not None
      else get_canonical_label_lookup()
    )

  def extract_text_from_docx(self, docx_bytes: bytes) -> str:
    """Extrae todo el texto plano del DOCX, incluyendo tablas, en orden real."""
    try:
      doc = Document(BytesIO(docx_bytes))
      text = []
      for block in doc.element.body:
        if block.tag == qn("w:p"):
          from docx.text.paragraph import Paragraph

          p = Paragraph(block, doc)
          if p.text.strip():
            text.append(p.text)
        elif block.tag == qn("w:tbl"):
          from docx.table import Table

          table = Table(block, doc)
          for row in table.rows:
            row_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if row_text:
              text.append(" | ".join(row_text))
      return "\n".join(text)
    except Exception as e:
      logger.error(f"Error leyendo DOCX crudo: {e}", exc_info=True)
      return ""

  def _normalizar_semanas(self, semanas: Any) -> List[Dict[str, Any]]:
    """Garantiza que semanas sea una lista de dicts con los campos esperados."""
    if not isinstance(semanas, list):
      return []
    normalizadas = []
    for s in semanas:
      if not isinstance(s, dict):
        continue
      teoria = s.get("teoria")
      teoria_en = s.get("teoria_en")
      herramientas = s.get("laboratorio_herramientas")
      normalizadas.append({
        "numero": s.get("numero"),
        "teoria": teoria if isinstance(teoria, list) else [],
        "teoria_en": teoria_en if isinstance(teoria_en, list) else [],
        "laboratorio_herramientas": herramientas if isinstance(herramientas, list) else [],
        "administrativo": bool(s.get("administrativo", False)),
      })
    return normalizadas

  def extract_and_save(
      self,
      docx_bytes: bytes,
      drive_file_id: str,
      filename: str = "",
      propietario_email: str = "legacy@upao.edu.pe",
  ) -> Optional[int]:
      """Extracción de un sílabo y persistencia del perfil técnico en la DB."""
      try:
          full_text = self.extract_text_from_docx(docx_bytes)
          if not full_text:
              logger.error(f"DOCX vacio o ilegible: {filename}")
              return None

          logger.info(f"Extrayendo silabo con LLM: {filename}")

          resultado_directo = run_async(
              self.llm_client.generate_flash_lite_json(
                  prompt_directo_silabo(full_text), label="Silabo-directo"
              )
          )

          if not isinstance(resultado_directo, dict) or not resultado_directo:
              logger.error(f"Fallo en extraccion IA de silabo: {filename}")
              return None

          nombre = resultado_directo.get("nombre") or filename.replace(".docx", "").replace("_", " ")
          if nombre:
              nombre = nombre.strip().capitalize()

          try:
              ciclo = int(resultado_directo.get("ciclo", 1))
          except (TypeError, ValueError):
              ciclo = 1

          semanas = self._normalizar_semanas(resultado_directo.get("semanas", []))

          menciones_tecnicas = []
          for sem in semanas:
              teorias_es = sem.get("teoria", [])
              teorias_en = sem.get("teoria_en", [])
              for i, t_es in enumerate(teorias_es):
                  if not isinstance(t_es, str):
                      continue
                  t_en = teorias_en[i] if i < len(teorias_en) else ""
                  menciones_tecnicas.append({
                      "termino": t_es,
                      "termino_en": t_en if isinstance(t_en, str) else "",
                      "seccion": f"semana_{sem.get('numero')}",
                      "explicito": True,
                  })

              for lab in sem.get("laboratorio_herramientas", []):
                  if isinstance(lab, str):
                      menciones_tecnicas.append({
                          "termino": lab,
                          "termino_en": lab,
                          "seccion": f"semana_{sem.get('numero')}",
                          "explicito": True,
                      })

          normalizados = TechnicalTermNormalizer.normalize_many(
              menciones_tecnicas,
              canonical_lookup=self.canonical_lookup,
          )
          if normalizados.rejected:
              resumen = ", ".join(
                  f"{item.term or '<vacío>'}:{item.reason}"
                  for item in normalizados.rejected[:10]
              )
              logger.warning(
                  "Se descartaron %s términos inválidos del sílabo %s: %s",
                  len(normalizados.rejected),
                  filename,
                  resumen,
              )
          perfil_tecnico = normalizados.profile
          if not perfil_tecnico:
              logger.error(
                  "El sílabo no produjo términos bilingües válidos; no se sobrescribe el perfil: %s",
                  filename,
              )
              return None

          curso = self.curso_repo.get_or_create(
              drive_file_id=drive_file_id,
              nombre=nombre,
              ciclo=ciclo,
              propietario_email=propietario_email,
          )
          self.curso_repo.update_profile(
              curso_id=curso.id,
              nombre=nombre,
              ciclo=ciclo,
              perfil_tecnico=perfil_tecnico,
          )

          self.db.commit()
          logger.info(f"Curso guardado (Perfil Tecnico listo): id={curso.id}, nombre={nombre}")
          return curso.id

      except Exception as e:
          logger.error(f"Error en CursoService.extract_and_save: {e}", exc_info=True)
          try:
              self.db.rollback()
          except Exception as rollback_err:
              logger.error(f"Error en rollback: {rollback_err}")
          return None
