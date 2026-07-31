"""
Servicio de orquestación para matching docente-curso.

Usa los repositorios de la fase 1 para cargar nodos y calcula un ranking
determinista basado en cobertura de la taxonomía compartida.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.database.models import CursoNodo, DocenteNodo
from backend.repositories.curso_repo import CursoRepository
from backend.repositories.docente_repo import DocenteRepository
from backend.services.explanation_service import ExplanationService
from backend.taxonomy.catalog import get_taxonomy
from backend.taxonomy.resolver import TaxonomyResolver
from backend.core.config import settings

logger = logging.getLogger(__name__)

COVERAGE_THRESHOLD = 0.55


def _termino_para_mostrar(evidencias: Optional[list], fallback: str) -> str:
  """
  Etiqueta legible para explicaciones: prioriza el término original del
  documento (español del sílabo/CV) sobre el nombre canónico de la taxonomía
  (ACM/SFIA en inglés).
  """
  for e in evidencias or []:
    if not isinstance(e, dict):
      continue
    term = (e.get("termino") or e.get("es") or "").strip()
    if term:
      return term
  return (fallback or "").strip() or "Requisito"


class MatchingService:
  """
  Calcula rankings de docentes para un curso usando la taxonomía compartida.

  El score de cobertura se calcula como promedio ponderado por
  peso_centralidad del curso sobre el total fijo de requisitos. El umbral
  solo marca brechas en las explicaciones; nunca descarta nodos del
  denominador.
  """

  def __init__(self, db: Session):
    self.db = db
    self.curso_repo = CursoRepository(db)
    self.docente_repo = DocenteRepository(db)
    self.resolver = TaxonomyResolver(get_taxonomy(settings.taxonomy_path))
    self.taxonomy = self.resolver.taxonomy

  def rank_for_curso(self, curso_id: int, top_k: int = 10, workspaces: Optional[List[str]] = None) -> List[dict]:
    """
    Retorna los top_k docentes mejor alineados con el curso indicado.

    Returns:
      Lista de dicts con docente_id, nombre, score_combinado, evidencias,
      brechas y xai_explanations.
    """
    try:
      curso = self.curso_repo.get_by_id(curso_id)
      if not curso:
        logger.warning(f"[MatchingService] Curso {curso_id} no encontrado")
        return []

      curso_nodos = self.curso_repo.get_nodos(curso_id)
      if not curso_nodos:
        logger.warning(
          f"[MatchingService] Curso {curso_id} no tiene nodos resueltos"
        )
        return []

      docentes = self.docente_repo.get_all(workspaces=workspaces)
      if not docentes:
        return []

      peso_total_curso = sum(cn.peso_centralidad for cn in curso_nodos)
      if peso_total_curso == 0:
        logger.warning(
          f"[MatchingService] Curso {curso_id} tiene peso total cero"
        )
        return []

      resultados: List[dict] = []
      for docente in docentes:
        docente_nodos = self.docente_repo.get_nodos(docente.id)
        if not docente_nodos:
          continue

        score, matches, brechas = self._match_docente(
          curso_nodos, docente_nodos, peso_total_curso
        )
        matches_atomicos = self._to_matches_atomicos(matches)

        resultados.append(
          {
                                    "docente_id": docente.id,
                        "nombre": docente.nombre,
                        "grado": docente.grado,
                        "score_combinado": round(score * 100, 2),
                        "perfil_tecnico": docente.perfil_tecnico,
                        "xai_explanations": ExplanationService.generate(
                            matches_atomicos, brechas
                        ),
                    }
        )

      resultados.sort(key=lambda r: r["score_combinado"], reverse=True)
      return resultados[:top_k]
    except Exception as e:
      logger.error(
        f"[MatchingService] Error generando ranking para curso {curso_id}: {e}",
        exc_info=True,
      )
      return []

  def _match_docente(
    self,
    curso_nodos: List[CursoNodo],
    docente_nodos: List[DocenteNodo],
    peso_total_curso: float,
  ) -> tuple:
    """
    Calcula score, matches atómicos y brechas para un docente contra un curso.

    Para cada nodo del curso se usa max-pooling: se busca el mejor match
    entre todos los nodos del docente.
    """
    weighted_sum = 0.0
    matches: List[Dict[str, Any]] = []
    brechas: List[dict] = []

    for cn in curso_nodos:
      best_score, best_dn = self._best_match_for_curso_node(cn, docente_nodos)
      weighted_sum += best_score * cn.peso_centralidad

      nodo_curso = self.taxonomy.get_node(cn.nodo_id)
      tax_curso = nodo_curso.name if nodo_curso else cn.nodo_id
      # Mostrar en español: mención del sílabo, no el id ACM en inglés
      curso_name = _termino_para_mostrar(cn.evidencias, tax_curso)

      match_info: Dict[str, Any] = {
        "curso_nodo_id": cn.nodo_id,
        "curso_nodo_name": curso_name,
        "curso_nodo_name_tax": tax_curso,
        "docente_nodo_id": best_dn.nodo_id if best_dn else None,
        "docente_nodo_name": None,
        "score": best_score,
        "peso_centralidad": cn.peso_centralidad,
        "cubierto": best_score >= COVERAGE_THRESHOLD,
        "evidencia_docente": None,
        "evidencia_curso": (cn.evidencias or [None])[0] if cn.evidencias else None,
      }

      if best_dn:
        nodo_docente = self.taxonomy.get_node(best_dn.nodo_id)
        tax_doc = nodo_docente.name if nodo_docente else best_dn.nodo_id
        match_info["docente_nodo_name"] = _termino_para_mostrar(
          best_dn.evidencias, tax_doc
        )
        match_info["docente_nodo_name_tax"] = tax_doc
        evidencias = best_dn.evidencias or []
        if evidencias:
          match_info["evidencia_docente"] = evidencias[0]

      matches.append(match_info)

      if best_score < COVERAGE_THRESHOLD:
        brechas.append(
          {
            "curso_nodo_id": cn.nodo_id,
            "curso_nodo_name": curso_name,
            "peso_centralidad": cn.peso_centralidad,
            "mejor_score_docente": best_score,
            "semanas": cn.semanas,
          }
        )

    score = weighted_sum / peso_total_curso

    # Ordenar por contribución al score para priorizar en explicaciones
    matches.sort(key=lambda m: m["score"] * m["peso_centralidad"], reverse=True)
    brechas.sort(key=lambda b: b["peso_centralidad"], reverse=True)

    return score, matches, brechas

  def _best_match_for_curso_node(
    self,
    curso_nodo: CursoNodo,
    docente_nodos: List[DocenteNodo],
  ) -> tuple:
    """Max-pooling: retorna el mejor match docente para un nodo de curso."""
    best_score = 0.0
    best_dn: Optional[DocenteNodo] = None

    for dn in docente_nodos:
      score = self._score_pair(curso_nodo.nodo_id, dn.nodo_id)
      if score > best_score:
        best_score = score
        best_dn = dn

    return best_score, best_dn

  def _score_pair(self, curso_nodo_id: str, docente_nodo_id: str) -> float:
    """
    Score entre dos nodos basado en el grafo taxonómico versionado.

    El grafo combina las jerarquías originales con relaciones tipadas entre
    fuentes. ``semantic_similarity`` maximiza el producto de pesos y limita la
    longitud del camino para que relaciones débiles o remotas no se conviertan
    en cobertura artificial.
    """
    return self.taxonomy.semantic_similarity(
      curso_nodo_id,
      docente_nodo_id,
      max_hops=4,
    )

  def _to_matches_atomicos(self, matches: List[Dict[str, Any]]) -> List[dict]:
    """Convierte matches internos al formato atómico esperado por XAI (términos en español)."""
    atomicos = []
    for m in matches:
      if not m["cubierto"]:
        continue
      evidencia = m["evidencia_docente"] or {}
      # Preferir mención original del CV si existe; si no, el label ya resuelto en español
      docente_label = (
        (evidencia.get("termino") or "").strip()
        or m.get("docente_nodo_name")
        or "No disponible"
      )
      curso_ev = m.get("evidencia_curso") or {}
      curso_label = (
        (curso_ev.get("termino") or "").strip()
        or m.get("curso_nodo_name")
        or "Requisito del curso"
      )
      atomicos.append(
        {
          "curso_entidad": curso_label,
          "docente_entidad": docente_label,
          "score": round(m["score"], 3),
          "peso_centralidad": m["peso_centralidad"],
          "explicito": evidencia.get("explicito", True),
          "evidencia_texto": evidencia.get("contexto", ""),
          "evidencia_termino": evidencia.get("termino", ""),
          "evidencia_seccion": evidencia.get("seccion", ""),
        }
      )
    return atomicos
