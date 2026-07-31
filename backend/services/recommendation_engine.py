"""
Motor de recomendaciones de docentes para cursos.

Este módulo es una fachada que orquesta:
 - MatchingService: ranking por taxonomía de nodos (score + brechas + XAI).
 - CRUD de caché de recomendaciones.

La lógica de scoring y explicaciones deterministas vive en MatchingService;
RecommendationEngine solo se encarga de cacheo, saneamiento de historial y
presentación al API.
"""

import logging
from typing import List, Dict, Optional

from sqlalchemy.orm import Session

from backend.database import crud
from backend.database.models import Docente
from backend.llm.client import GeminiClient
from backend.services.matching_service import MatchingService

logger = logging.getLogger(__name__)


class RecommendationEngine:
  """Fachada de recomendaciones con cacheo y explicaciones deterministas."""

  def __init__(
    self,
    llm_client: Optional[GeminiClient] = None,
    use_nlg: bool = False,
  ):
    self.llm_client = llm_client
    self.use_nlg = use_nlg
    if use_nlg:
      logger.warning(
        "[RecommendationEngine] use_nlg=True ya no tiene efecto; "
        "las explicaciones son deterministas."
      )

  def _saneamiento_diferido(self, db: Session, docentes: List[Docente]) -> None:
    """Elimina historiales cuyo nombre_docente no tenga match >= 0.8 con ningún docente activo."""
    import unicodedata
    import re

    def normalize_name(s: str) -> List[str]:
      s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("utf-8")
      s = re.sub(r"[^A-Z0-9 ]", " ", s.upper())
      return s.split()

    def match_score(nombre_hist: str, nombre_bd: str) -> float:
      words_a = normalize_name(nombre_hist)
      words_b = normalize_name(nombre_bd)
      shorter, longer = (words_a, words_b) if len(words_a) <= len(words_b) else (words_b, words_a)
      matches = sum(1 for w in shorter if w in longer)
      return matches / len(shorter) if shorter else 0.0

    docentes_cache = {d.nombre.strip().upper(): d for d in docentes if d.nombre}
    all_historial = crud.get_all_historiales(db)

    to_delete = []
    for h in all_historial:
      best_score = max(
        (match_score(h.nombre_docente, nombre_bd) for nombre_bd in docentes_cache.keys()),
        default=0.0,
      )
      if best_score < 0.8:
        to_delete.append(h)

    if to_delete:
      logger.info(f"🧹 Saneamiento diferido: Eliminando {len(to_delete)} historiales huérfanos.")
      for h in to_delete:
        db.delete(h)
      db.commit()

  def _save_node_recommendations_cache(
    self,
    db: Session,
    curso_id: int,
    recommendations: List[dict],
  ) -> None:
    """Guarda resultados del motor de nodos en RecomendacionCache."""
    recs_to_save = []
    for rec in recommendations:
      rec_save = rec.copy()
      rec_save["shap_explanations"] = {
        "text": rec.get("xai_explanations", ""),
        "brechas": rec.get("brechas", []),
        "matches_atomicos": rec.get("evidencias", {}).get("matches_atomicos", []),
      }
      rec_save["version_algoritmo"] = "node_taxonomy_v1.1"
      rec_save["score_est"] = rec.get("score_nodos", 0.0)
      rec_save["score_tac"] = 0.0
      recs_to_save.append(rec_save)

    try:
      crud.save_recomendaciones_cache(
        db, curso_id, recs_to_save, version_algoritmo="node_taxonomy_v1.1"
      )
    except Exception as e:
      logger.error(f"Error guardando caché de nodos: {e}")

  def _load_node_recommendations_cache(
    self,
    db: Session,
    cached_entries: List,
    top_k: int,
  ) -> List[dict]:
    """Reconstruye respuesta de API desde caché del motor de nodos."""
    recommendations = []
    for cache_entry in cached_entries[:top_k]:
      docente = crud.get_docente_by_id(db, cache_entry.docente_id)
      if not docente:
        continue
      shap = cache_entry.shap_explanations or {}
      score_combinado = round(cache_entry.score_combinado, 2)
      recommendations.append({
        "docente_id": docente.id,
        "nombre": docente.nombre,
        "grado": docente.grado,
                "score_combinado": score_combinado,
                "perfil_tecnico": docente.perfil_tecnico,
                "xai_explanations": shap.get("text", ""),
                "from_cache": True,
      })

    return recommendations

  def recommend_docentes_for_curso(
    self,
    db: Session,
    curso_id: int,
    top_k: int = 10,
    use_cache: bool = True,
    cache_max_age_days: int = 7,
    workspaces: Optional[List[str]] = None,
  ) -> List[Dict]:
    """
    Genera el ranking de docentes para un curso.

    Mantiene la misma firma y formato de respuesta que versiones anteriores
    para no romper la API.
    """
    try:
      # 1. Revisar caché
      if use_cache:
        cached = crud.get_recomendaciones_cache(db, curso_id, max_age_days=cache_max_age_days)
        if cached and len(cached) >= top_k:
          # v1.1: términos de explicación en español (mención del documento)
          if all(c.version_algoritmo == "node_taxonomy_v1.1" for c in cached):
            return self._load_node_recommendations_cache(db, cached, top_k)

      # 2. Saneamiento de historial
      docentes = crud.get_all_docentes(db, workspaces=workspaces)
      self._saneamiento_diferido(db, docentes)

      # 3. Matching por taxonomía
      matching_service = MatchingService(db)
      recommendations = matching_service.rank_for_curso(curso_id, top_k=top_k, workspaces=workspaces)
      if not recommendations:
        return []

      # 4. Score relativo al mejor candidato
      winner_score = recommendations[0]["score_combinado"]
      for rec in recommendations:
        rec["score_relativo"] = round(
          (rec["score_combinado"] / winner_score) * 100, 2
        ) if winner_score > 0 else 0

      # 5. Guardar en caché
      if use_cache:
        self._save_node_recommendations_cache(db, curso_id, recommendations)

      return recommendations

    except Exception as e:
      logger.error(
        f"Error al generar recomendaciones para el curso {curso_id}: {e}",
        exc_info=True,
      )
      return []


recommendation_engine = RecommendationEngine()
