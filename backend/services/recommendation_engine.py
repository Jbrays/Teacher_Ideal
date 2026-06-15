import os
# ¡CRÍTICO! Apagar el internet ANTES de importar sentence_transformers
os.environ["HF_HOME"] = "/app/.cache/huggingface"
os.environ["SENTENCE_TRANSFORMERS_HOME"] = "/app/.cache/sbert"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from typing import List, Dict
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from scipy.optimize import linear_sum_assignment
import vertexai
from vertexai.generative_models import GenerativeModel
from sqlalchemy.orm import Session
from backend.services.embeddings_manager import embeddings_manager
from backend.database import crud
from backend.database.models import Curso, Docente

import logging
import os

logger = logging.getLogger(__name__)

# Variable global para lazy loading
_sbert_model = None

def get_sbert_model():
    global _sbert_model
    if _sbert_model is None:
        logger.info("Cargando modelo Qwen Embeddings a memoria por primera vez...")
        try:
            # Carga offline forzada por variables de entorno (requiere trust_remote_code)
            _sbert_model = SentenceTransformer('Qwen/Qwen3-Embedding-0.6B', trust_remote_code=True)
            _sbert_model.half()
            logger.info("Modelo Qwen cargado exitosamente.")
        except Exception as e:
            logger.error(f"Error cargando Qwen: {e}", exc_info=True)
    return _sbert_model


class RecommendationEngine:
    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-3.1-flash-lite")
        try:
            vertexai.init(project=self.project_id, location=self.location)
            self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-3.1-flash-lite")
            self.gemini_model = GenerativeModel(self.model_name)
        except Exception as e:
            logger.error(f"Error iniciando Vertex AI para NLG: {e}", exc_info=True)
            self.gemini_model = None



    def get_embedding_for_curso_text(self, text: str) -> np.ndarray:
        model = get_sbert_model()
        if not model:
            raise Exception("Modelo SBERT no cargado")
        prompt = "Área de conocimiento que debe dominar un docente universitario para dictar este curso: "
        return model.encode([text], prompt=prompt, truncate_dim=512, convert_to_numpy=True)[0].reshape(1, -1)

    def get_embedding_for_docente_text(self, text: str) -> np.ndarray:
        model = get_sbert_model()
        if not model:
            raise Exception("Modelo SBERT no cargado")
        prompt = "Área de conocimiento técnico que define el perfil académico de este docente universitario: "
        return model.encode([text], prompt=prompt, truncate_dim=512, convert_to_numpy=True)[0].reshape(1, -1)

    def _generate_nlg_explanation(self, winning_matches: List[Dict]) -> str:
        if not self.gemini_model or not winning_matches:
            return "Evidencias del match:\n* El docente posee competencias alineadas con la materia."
            
        evidencia_text = "\\n".join([f"- Sílabo exige: {m['curso_entidad']} <-> Docente posee: {m['docente_entidad']} (Similitud: {m['score']*100:.1f}%)" for m in winning_matches])
        
        prompt = f"""
Convierte las evidencias de match en bullets. Nada más.

EJEMPLO DE ENTRADA (Exactamente como llega el dato):
- Sílabo exige: Modelado de procesos <-> Docente posee: BPMN (Similitud: 91.5%)
- Sílabo exige: Cloud Computing <-> Docente posee: Sistemas de Información (Similitud: 54.0%)
- Sílabo exige: Estrategias metodológicas <-> Docente posee: Flipped Learning (Similitud: 73.0%)

EJEMPLO DE SALIDA ESPERADA:
Evidencias del match:
* BPMN cubre Modelado de procesos (91.5%)
* Flipped Learning — coincidencia parcial con Estrategias metodológicas (73.0%)
* Sistemas de Información — coincidencia débil con Cloud Computing (54.0%) [débil]

REGLAS:
1. Empieza siempre con "Evidencias del match:" sin excepción.
2. Máximo 8 bullets, ordenados de mayor a menor similitud.
3. Si la entidad supera 5 palabras, abrevia al concepto central.
   Ejemplo:
   "Metodologías de implementación de sistemas ERP" → "Impl. ERP"

4. Clasificación por similitud:
   - 80% o más  → "X cubre Y (score%)"
   - 60% a 79% → "X — coincidencia parcial con Y (score%)"
   - menos de 60% → "X — coincidencia débil con Y (score%) [débil]"

5. Si no hay evidencias o el campo llega vacío:
   escribe únicamente:
   "Sin evidencias de match directo."

6. Prohibido:
   - adjetivos valorativos
   - frases de cierre
   - explicaciones
   - cualquier texto fuera de los bullets

7. Si un bullet supera 15 palabras después de abreviar,
   corta en 15 palabras y agrega "…"

EVIDENCIAS:
{evidencia_text}
"""
        try:
            response = self.gemini_model.generate_content(
                prompt,
                generation_config={"temperature": 0.2, "max_output_tokens": 512}
            )
            text = response.text.strip()
            if not text.startswith("Evidencias"):
                text = "Evidencias del match:\n" + text
            return text
        except Exception as e:
            logger.error(f"Error generando explicación NLG: {e}", exc_info=True)
            return "Evidencias del match:\n* Perfil técnico alineado con las competencias de la materia."

    def _generate_nlg_explanations_batch(self, results_list: List[Dict]) -> List[str]:
        if not self.gemini_model or not results_list:
            return ["Evidencias del match:\n* El docente posee competencias alineadas con la materia." for _ in results_list]
        
        sections = []
        for i, result in enumerate(results_list):
            matches = result.get('evidencias', {}).get('matches_atomicos', [])
            if not matches:
                sections.append(f"### Docente {i+1}\nSin evidencias.")
                continue
            evidencia_text = "\n".join([f"- Sílabo exige: {m['curso_entidad']} <-> Docente posee: {m['docente_entidad']} (Similitud: {m['score']*100:.1f}%)" for m in matches])
            sections.append(f"### Docente {i+1}\n{evidencia_text}")
        
        all_sections = "\n\n".join(sections)
        
        prompt = f"""Convierte las evidencias de match en bullets para CADA docente. Separa la respuesta de cada docente con la línea exacta: ---SEPARADOR---

EJEMPLO DE SALIDA PARA UN DOCENTE:
Evidencias del match:
* BPMN cubre Modelado de procesos (91.5%)
* Flipped Learning — coincidencia parcial con Estrategias metodológicas (73.0%)
* Sistemas de Información — coincidencia débil con Cloud Computing (54.0%) [débil]

REGLAS:
1. Empieza siempre con "Evidencias del match:" para CADA docente.
2. Máximo 8 bullets por docente, ordenados de mayor a menor similitud.
3. Si la entidad supera 5 palabras, abrevia al concepto central.
4. Clasificación por similitud:
   - 80% o más  → "X cubre Y (score%)"
   - 60% a 79% → "X — coincidencia parcial con Y (score%)"
   - menos de 60% → "X — coincidencia débil con Y (score%) [débil]"
5. Si no hay evidencias: "Sin evidencias de match directo."
6. Prohibido: adjetivos valorativos, frases de cierre, explicaciones.
7. Si un bullet supera 15 palabras, corta en 15 y agrega "…"
8. IMPORTANTE: Separa CADA docente con la línea exacta: ---SEPARADOR---

EVIDENCIAS DE {len(results_list)} DOCENTES:
{all_sections}
"""
        try:
            response = self.gemini_model.generate_content(
                prompt,
                generation_config={"temperature": 0.2, "max_output_tokens": 4096}
            )
            full_text = response.text.strip()
            parts = [p.strip() for p in full_text.split("---SEPARADOR---")]
            
            results = []
            for part in parts:
                if not part:
                    continue
                if not part.startswith("Evidencias"):
                    part = "Evidencias del match:\n" + part
                results.append(part)
            
            if len(results) == len(results_list):
                return results
            
            logger.warning(f"NLG batch: esperaba {len(results_list)} secciones, obtuvo {len(results)}. Usando fallback individual.")
            return [self._generate_nlg_explanation(r.get('evidencias', {}).get('matches_atomicos', [])) for r in results_list]
            
        except Exception as e:
            logger.error(f"Error en NLG batch: {e}", exc_info=True)
            return [self._generate_nlg_explanation(r.get('evidencias', {}).get('matches_atomicos', [])) for r in results_list]

    def _saneamiento_diferido(self, db: Session, docentes: List[Docente]):
        """Elimina historiales cuyo nombre_docente no tiene match >= 0.8 con ningún docente activo."""
        import unicodedata
        import re
        
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

        docentes_cache = {d.nombre.strip().upper(): d for d in docentes if d.nombre}
        all_historial = crud.get_all_historiales(db)
        
        to_delete = []
        for h in all_historial:
            best_score = 0
            for nombre_bd in docentes_cache.keys():
                score = match_score(h.nombre_docente, nombre_bd)
                if score > best_score:
                    best_score = score
            if best_score < 0.8:
                to_delete.append(h)
                
        if to_delete:
            logger.info(f"🧹 Saneamiento diferido: Eliminando {len(to_delete)} historiales huérfanos sin match activo.")
            for h in to_delete:
                db.delete(h)
            db.commit()

    def _avg_similarity_vs_temas(
        self,
        source_text: str,
        temas_curso: List[str],
        source_is_docente: bool = True
    ) -> float:
        """
        Calcula la similitud promedio de un texto (entidad/competencia del docente)
        contra todos los temas del curso.
        """
        if not source_text or not temas_curso:
            return 0.0

        try:
            if source_is_docente:
                source_vec = self.get_embedding_for_docente_text(source_text)
            else:
                source_vec = self.get_embedding_for_curso_text(source_text)

            tema_vectors = embeddings_manager.get_entity_embeddings(
                temas_curso,
                self.get_embedding_for_curso_text,
                is_curso=True
            )
            if not tema_vectors:
                return 0.0

            valid_temas = [t for t in temas_curso if t in tema_vectors]
            if not valid_temas:
                return 0.0

            target_matrix = np.array([tema_vectors[t] for t in valid_temas])
            if target_matrix.ndim == 3:
                target_matrix = np.squeeze(target_matrix, axis=1)

            sim_matrix = cosine_similarity(source_vec, target_matrix)
            return float(np.mean(sim_matrix))
        except Exception as e:
            logger.warning(f"Error calculando similitud para '{source_text[:50]}': {e}")
            return 0.0

    def _evaluar_docente_vs_temas(
        self,
        docente: Docente,
        temas_curso: List[str],
        threshold: float = 0.55
    ) -> tuple:
        """
        Evalúa un docente contra los temas del curso.
        Retorna (score_final, evidencias).
        """
        scores_validos = []
        evidencias = []

        # Entidades del docente
        if docente.entidades_clave:
            for entidad in docente.entidades_clave:
                if not entidad or not entidad.strip():
                    continue
                avg_score = self._avg_similarity_vs_temas(entidad.strip(), temas_curso, source_is_docente=True)
                if avg_score >= threshold:
                    scores_validos.append(avg_score)
                    evidencias.append({
                        'tipo': 'entidad',
                        'texto': entidad.strip(),
                        'score_promedio': round(avg_score, 4)
                    })

        # Competencias del docente (divididas por comas)
        if docente.competencias_tecnicas:
            competencias = [c.strip() for c in docente.competencias_tecnicas.split(',') if c.strip()]
            for comp in competencias:
                avg_score = self._avg_similarity_vs_temas(comp, temas_curso, source_is_docente=True)
                if avg_score >= threshold:
                    scores_validos.append(avg_score)
                    evidencias.append({
                        'tipo': 'competencia',
                        'texto': comp,
                        'score_promedio': round(avg_score, 4)
                    })

        if not scores_validos:
            return 0.0, []

        score_final = sum(scores_validos) / len(scores_validos)
        return score_final, evidencias

    def recommend_docentes_for_curso(
        self,
        db: Session,
        curso_id: int,
        top_k: int = 10,
        use_cache: bool = True,
        cache_max_age_days: int = 7
    ) -> List[Dict]:
        try:
            curso = crud.get_curso_by_id(db, curso_id)
            if not curso: return []

            # Nuevo motor: requiere temas semanales
            temas_curso = curso.temas or []
            if not temas_curso:
                logger.warning(f"Curso {curso_id} no tiene temas semanales. No se pueden generar recomendaciones.")
                return []

            docentes = crud.get_all_docentes(db)
            self._saneamiento_diferido(db, docentes)

            THRESHOLD = 0.55
            final_scores = []

            for docente in docentes:
                score, evidencias = self._evaluar_docente_vs_temas(docente, temas_curso, THRESHOLD)
                if score <= 0:
                    continue

                final_scores.append({
                    'docente_id': docente.id,
                    'docente_obj': docente,
                    'score_combinado': score,
                    'evidencias': evidencias
                })

            final_scores.sort(key=lambda x: x['score_combinado'], reverse=True)
            top_results = final_scores[:top_k]

            if not top_results:
                return []

            winner_score = top_results[0]['score_combinado']

            recommendations_to_save = []
            recommendations_for_api = []

            for idx, result in enumerate(top_results):
                docente = result['docente_obj']
                score_abs = result['score_combinado']

                if score_abs >= 0.80: conf_tag = "Confianza Muy Alta"
                elif score_abs >= 0.60: conf_tag = "Confianza Alta"
                elif score_abs >= 0.40: conf_tag = "Confianza Media"
                else: conf_tag = "Confianza Baja"

                score_rel = (score_abs / winner_score) if winner_score > 0 else 0

                # Generar explicación XAI simple sin llamar a Gemini
                evidencias = result.get('evidencias', [])
                xai_lines = ["Evidencias del match:"]
                if evidencias:
                    for ev in sorted(evidencias, key=lambda x: x['score_promedio'], reverse=True)[:8]:
                        xai_lines.append(f"* {ev['texto']} ({ev['score_promedio']*100:.1f}%)")
                else:
                    xai_lines.append("* Sin evidencias de match directo.")
                xai_text = "\n".join(xai_lines)

                rec_data = {
                    'docente_id': docente.id,
                    'nombre': docente.nombre,
                    'email': docente.email,
                    'grado': docente.grado,
                    'entidades_clave': docente.entidades_clave,
                    'score_combinado': round(score_abs * 100, 2),
                    'score_est': round(score_abs * 100, 2),
                    'score_tac': 0.0,
                    'score_historico': 0.0,
                    'score_semantico': round(score_abs * 100, 2),
                    'score_relativo': round(score_rel * 100, 2),
                    'confianza_etiqueta': conf_tag,
                    'evidencias': {
                        'entidades_clave': [ev['texto'] for ev in evidencias if ev['tipo'] == 'entidad'][:5],
                        'competencias': [ev['texto'] for ev in evidencias if ev['tipo'] == 'competencia'][:5],
                        'entradas_validas': evidencias
                    },
                    'xai_explanations': xai_text,
                    'from_cache': False
                }

                recommendations_for_api.append(rec_data)

                rec_save = rec_data.copy()
                rec_save['shap_explanations'] = {'text': xai_text}
                rec_save['version_algoritmo'] = conf_tag
                recommendations_to_save.append(rec_save)

            if use_cache:
                from backend.database.db_session import SessionLocal
                db_temp = SessionLocal()
                try:
                    crud.save_recomendaciones_cache(
                        db_temp, curso_id, recommendations_to_save, version_algoritmo="temas_v1.0"
                    )
                except Exception as cache_error:
                    logger.error(f"Error guardando caché diferido: {cache_error}")
                finally:
                    db_temp.close()

            return recommendations_for_api

        except Exception as e:
            import traceback
            logger.error(f"Error al generar recomendaciones para el curso {curso_id}: {e}", exc_info=True)
            traceback.print_exc()
            return []

recommendation_engine = RecommendationEngine()