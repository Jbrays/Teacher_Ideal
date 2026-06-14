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

    def recommend_docentes_for_curso(
        self,
        db: Session,
        curso_id: int,
        top_k: int = 10,
        use_cache: bool = True,
        cache_max_age_days: int = 7
    ) -> List[Dict]:
        try:
            # 1. Intentar usar Cache L1
            if use_cache:
                cached_recommendations = crud.get_recomendaciones_cache(db, curso_id, max_age_days=cache_max_age_days)
                if cached_recommendations and len(cached_recommendations) >= top_k:
                    recommendations = []
                    for cache_entry in cached_recommendations[:top_k]:
                        docente = crud.get_docente_by_id(db, cache_entry.docente_id)
                        if not docente: continue
                        
                        recommendations.append({
                            'docente_id': docente.id,
                            'nombre': docente.nombre,
                            'email': docente.email,
                            'grado': docente.grado,
                            'entidades_clave': docente.entidades_clave,
                            'score_combinado': round(cache_entry.score_combinado * 100, 2),
                            'score_est': round(cache_entry.score_est * 100, 2),
                            'score_tac': round(cache_entry.score_tac * 100, 2),
                            'score_relativo': round(cache_entry.score_combinado * 100, 2), # Se recalcula luego
                            'confianza_etiqueta': cache_entry.version_algoritmo, # Reciclado
                            'evidencias': cache_entry.evidencias if cache_entry.evidencias else {'entidades_clave': []},
                            'xai_explanations': cache_entry.shap_explanations.get('text', ''),
                            'from_cache': True
                        })
                    
                    # Recalcular score_relativo para el subset en caché
                    if recommendations:
                        max_score = recommendations[0]['score_combinado']
                        for rec in recommendations:
                            rec['score_relativo'] = round((rec['score_combinado'] / max_score) * 100, 2) if max_score > 0 else 0
                    return recommendations

            # 2. Si no hay cache, calcular desde cero
            curso = crud.get_curso_by_id(db, curso_id)
            if not curso: return []
            
            docentes = crud.get_all_docentes(db)
            
            # --- SANEAMIENTO DIFERIDO (Limpiar historiales huérfanos) ---
            self._saneamiento_diferido(db, docentes)

            # --- LÓGICA DE MATCH PURO ---
            W_EST = 0.7
            W_TAC = 0.3

            # Recolectar todos los strings para embeddear (Separados por Query y Document)
            todas_entidades_curso = set()
            todas_competencias_curso = set()
            todas_entidades_docente = set()
            todas_competencias_docente = set()
            
            if curso.entidades_clave:
                todas_entidades_curso.update(curso.entidades_clave)
            if curso.competencias_tecnicas:
                todas_competencias_curso.add(curso.competencias_tecnicas)

            for d in docentes:
                if d.entidades_clave:
                    todas_entidades_docente.update(d.entidades_clave)
                if d.competencias_tecnicas:
                    todas_competencias_docente.add(d.competencias_tecnicas)

            # Obtener vectores (aprovecha la caché local de SQLite en el manager con llaves separadas)
            entidades_curso_vectores = embeddings_manager.get_entity_embeddings(list(todas_entidades_curso), self.get_embedding_for_curso_text, is_curso=True)
            competencias_curso_vectores = embeddings_manager.get_entity_embeddings(list(todas_competencias_curso), self.get_embedding_for_curso_text, is_curso=True)
            
            entidades_docente_vectores = embeddings_manager.get_entity_embeddings(list(todas_entidades_docente), self.get_embedding_for_docente_text, is_curso=False)
            competencias_docente_vectores = embeddings_manager.get_entity_embeddings(list(todas_competencias_docente), self.get_embedding_for_docente_text, is_curso=False)
            
            if not curso.entidades_clave or not entidades_curso_vectores:
                return []
                
            c_entities = curso.entidades_clave
            c_vectors = np.array([entidades_curso_vectores[e] for e in c_entities if e in entidades_curso_vectores])
            if c_vectors.ndim == 3: c_vectors = np.squeeze(c_vectors, axis=1)
            if len(c_vectors) == 0: return []
            
            # Vector táctico del curso
            c_tac_vector = None
            if curso.competencias_tecnicas and curso.competencias_tecnicas in competencias_curso_vectores:
                c_tac_vector = np.array([competencias_curso_vectores[curso.competencias_tecnicas]])
                if c_tac_vector.ndim == 3: c_tac_vector = np.squeeze(c_tac_vector, axis=1)

            # Calcular Similitud Semántica (Match Estratégico S_EST y Match Táctico S_TAC)
            final_scores = []
            for docente in docentes:
                d_entities = docente.entidades_clave
                if not d_entities:
                    continue
                    
                d_vectors = np.array([entidades_docente_vectores[e] for e in d_entities if e in entidades_docente_vectores])
                if len(d_vectors) == 0:
                    continue
                if d_vectors.ndim == 3: d_vectors = np.squeeze(d_vectors, axis=1)
                
                # Matriz Coseno S_EST
                sim_matrix = cosine_similarity(c_vectors, d_vectors)
                
                # Asignación Lineal (Algoritmo Húngaro) para matching 1 a 1
                # linear_sum_assignment minimiza el costo, así que usamos 1 - similitud
                cost_matrix = 1.0 - sim_matrix
                row_ind, col_ind = linear_sum_assignment(cost_matrix)
                
                THRESHOLD = 0.55
                
                best_matches = []
                # El promedio se calcula sobre el total de entidades del curso, penalizando
                # a docentes que no pueden cubrir todas.
                total_curso_entidades = len(c_entities)
                sum_scores = 0.0
                
                for r, c in zip(row_ind, col_ind):
                    score = float(sim_matrix[r][c])
                    if score >= THRESHOLD:
                        sum_scores += score
                        best_matches.append({
                            'curso_entidad': c_entities[r],
                            'docente_entidad': d_entities[c],
                            'score': score
                        })
                
                s_est = sum_scores / total_curso_entidades if total_curso_entidades > 0 else 0.0
                
                best_matches.sort(key=lambda x: x['score'], reverse=True)
                top_evidencias = best_matches[:5]
                
                # Cálculo de S_TAC
                s_tac = 0.0
                if c_tac_vector is not None and docente.competencias_tecnicas and docente.competencias_tecnicas in competencias_docente_vectores:
                    d_tac_vector = np.array([competencias_docente_vectores[docente.competencias_tecnicas]])
                    if d_tac_vector.ndim == 3: d_tac_vector = np.squeeze(d_tac_vector, axis=1)
                    s_tac = float(cosine_similarity(c_tac_vector, d_tac_vector)[0][0])
                
                # Score Combinado (Match Puro sin penalizaciones)
                combined_score = (s_est * W_EST) + (s_tac * W_TAC)
                
                final_scores.append({
                    'docente_id': docente.id,
                    'docente_obj': docente,
                    'score_combinado': combined_score,
                    'score_est': s_est,
                    'score_tac': s_tac,
                    'evidencias': {'matches_atomicos': top_evidencias}
                })

            # 6. Ordenar por Score Final
            final_scores.sort(key=lambda x: x['score_combinado'], reverse=True)
            top_results = final_scores[:top_k]

            if not top_results:
                return []

            winner_score = top_results[0]['score_combinado']

            # 7. Formatear Resultados (XAI NLG, Relative Score, Confidence)
            recommendations_to_save = []
            recommendations_for_api = []
            
            # Solo generar NLG para los top 3 para ahorrar tiempo/costos
            nlg_results = self._generate_nlg_explanations_batch(top_results[:10])
            
            for idx, result in enumerate(top_results):
                docente = result['docente_obj']
                
                xai_text = nlg_results[idx] if idx < len(nlg_results) else ""
                
                # Etiqueta de Confianza Absoluta
                score_abs = result['score_combinado']
                if score_abs >= 0.80: conf_tag = "Confianza Muy Alta"
                elif score_abs >= 0.60: conf_tag = "Confianza Alta"
                elif score_abs >= 0.40: conf_tag = "Confianza Media"
                else: conf_tag = "Confianza Baja"

                # Score Relativo
                score_rel = (score_abs / winner_score) if winner_score > 0 else 0

                rec_data = {
                    'docente_id': docente.id,
                    'nombre': docente.nombre,
                    'email': docente.email,
                    'grado': docente.grado,
                    'entidades_clave': docente.entidades_clave,
                    'score_combinado': round(score_abs * 100, 2),
                    'score_est': round(result.get('score_est', 0) * 100, 2),
                    'score_tac': round(result.get('score_tac', 0) * 100, 2),
                    'score_historico': round(result.get('score_tac', 0) * 100, 2),
                    'score_semantico': round(result.get('score_est', 0) * 100, 2),
                    'score_relativo': round(score_rel * 100, 2),
                    'confianza_etiqueta': conf_tag,
                    'evidencias': result['evidencias'],
                    'xai_explanations': xai_text,
                    'from_cache': False
                }

                recommendations_for_api.append(rec_data)

                # Guardamos en el campo shap_explanations por compatibilidad de esquema
                rec_save = rec_data.copy()
                rec_save['shap_explanations'] = {'text': xai_text}
                rec_save['version_algoritmo'] = conf_tag # Reutilizamos campo para la confianza
                recommendations_to_save.append(rec_save)

            # 8. Guardar en Cache
            if use_cache:
                from backend.database.db_session import SessionLocal
                db_temp = SessionLocal()
                try:
                    crud.save_recomendaciones_cache(
                        db_temp, curso_id, recommendations_to_save, version_algoritmo="ashp_v1.0"
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