from typing import List, Dict
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from backend.services.embeddings_manager import embeddings_manager
from backend.database import crud
from backend.database.models import Curso, Docente
from backend.services.explanation_model import ExplanationModel

import logging
import os

logger = logging.getLogger(__name__)

# Forzar a HuggingFace a usar SOLO el modelo pre-horneado en Docker
# Evita el error "429 Too Many Requests" en Cloud Run
os.environ["HF_HUB_OFFLINE"] = "1"

# Variable global para lazy loading
_sbert_model = None

def get_sbert_model():
    global _sbert_model
    if _sbert_model is None:
        logger.info("Cargando modelo SBERT BAAI/bge-m3 a memoria por primera vez (esto puede tardar)...")
        try:
            _sbert_model = SentenceTransformer('BAAI/bge-m3')
            _sbert_model.half()
            logger.info("Modelo SBERT cargado exitosamente.")
        except Exception as e:
            logger.error(f"Error cargando SBERT: {e}")
    return _sbert_model

class RecommendationEngine:
    def __init__(self):
        self.explanation_model = ExplanationModel()

    def create_curso_text(self, curso: Curso) -> str:
        nombre_curso = f"Curso: {curso.nombre}. " * 3
        perfil = curso.perfil_sintetico or ""
        entidades = ", ".join(curso.entidades_clave) if curso.entidades_clave else ""
        return f"{nombre_curso} {perfil} Tecnologías y temas clave: {entidades}"

    def create_docente_text(self, docente: Docente) -> str:
        perfil = docente.perfil_sintetico or ""
        entidades = ", ".join(docente.entidades_clave) if docente.entidades_clave else ""
        return f"{perfil} Habilidades y experiencia técnica: {entidades}"

    def _calculate_ner_evidencias(self, curso: Curso, docente: Docente) -> Dict:
        curso_entidades = set(curso.entidades_clave) if curso.entidades_clave else set()
        docente_entidades = set(docente.entidades_clave) if docente.entidades_clave else set()
        return {
            "entidades_clave": list(curso_entidades.intersection(docente_entidades))
        }

    def get_embedding_for_text(self, text: str) -> np.ndarray:
        model = get_sbert_model()
        if not model:
            raise Exception("Modelo SBERT no cargado")
        return model.encode([text], convert_to_numpy=True)[0].reshape(1, -1)

    def recommend_docentes_for_curso(
        self,
        db: Session,
        curso_id: int,
        top_k: int = 20,
        history_weight: float = 0.4, # SUBIDO A 0.4 (40%) para dar peso a la experiencia
        similarity_weight: float = 0.6, # BAJADO A 0.6 (60%) para balancear
        use_cache: bool = True,
        cache_max_age_days: int = 7
    ) -> List[Dict]:
        try:
            # 1. Intentar usar Cache L1 (Base de Datos)
            if use_cache:
                cached_recommendations = crud.get_recomendaciones_cache(db, curso_id, max_age_days=cache_max_age_days)
                
                # FIX: Si el cache tiene menos elementos que los solicitados (ej: 5 vs 100), ignorar cache y recalcular.
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
                            'score_historico': round(cache_entry.score_historico * 100, 2),
                            'score_semantico': round(cache_entry.score_semantico * 100, 2),
                            'evidencias': cache_entry.evidencias,
                            'shap_explanations': cache_entry.shap_explanations,
                            'from_cache': True
                        })
                    return recommendations

            # 2. Si no hay cache, calcular desde cero
            curso = crud.get_curso_by_id(db, curso_id)
            if not curso: return []

            # --- LÓGICA DE VETERANOS (HISTORIAL) ---
            historial = crud.get_historial_by_curso(db, curso_id)
            
            # Contar cuántas veces ha dictado el curso cada docente
            docente_semesters_count = {}
            for h in historial:
                docente_id = h.docente_id
                docente_semesters_count[docente_id] = docente_semesters_count.get(docente_id, 0) + 1
            
            # Umbral para ser considerado "Experto/Veterano" (100% score histórico)
            # Si tienes horarios de 2016 a 2023 (aprox 14-16 semestres), 8 semestres es un buen nivel de experto.
            VETERAN_THRESHOLD = 8 
            # ---------------------------------------

            # 3. Obtener Embeddings
            curso_embedding = embeddings_manager.get_or_create_embedding(
                db_item=curso,
                text_generator=self.create_curso_text,
                embedding_generator=self.get_embedding_for_text
            )

            docentes = crud.get_all_docentes(db)
            docentes_embeddings_map = embeddings_manager.get_all_docente_embeddings(
                db=db,
                docentes=docentes,
                text_generator=self.create_docente_text,
                embedding_generator=self.get_embedding_for_text
            )
            
            if not docentes_embeddings_map: return []

            docente_ids = list(docentes_embeddings_map.keys())
            docentes_vectors = np.array([docentes_embeddings_map[id] for id in docente_ids])
            
            # Asegurar que sea 2D
            if docentes_vectors.ndim == 3:
                docentes_vectors = np.squeeze(docentes_vectors, axis=1)

            # 4. Calcular Similitud Semántica (SBERT)
            similarities = cosine_similarity(curso_embedding, docentes_vectors)[0]

            # 5. Calcular Score Final
            final_scores = []
            for idx, docente_id in enumerate(docente_ids):
                docente = crud.get_docente_by_id(db, docente_id)
                if not docente: continue
                
                semantic_score = float(similarities[idx])
                
                # Score Histórico Gradual (0.0 a 1.0 basado en experiencia)
                semesters_taught = docente_semesters_count.get(docente_id, 0)
                history_score = min(semesters_taught / VETERAN_THRESHOLD, 1.0)
                
                combined_score = (history_score * history_weight) + (semantic_score * similarity_weight)
                
                evidencias = self._calculate_ner_evidencias(curso, docente)
                
                final_scores.append({
                    'docente_id': docente.id,
                    'docente_obj': docente,
                    'score_combinado': combined_score,
                    'score_historico': history_score,
                    'score_semantico': semantic_score,
                    'evidencias': evidencias,
                    'shap_explanations': {} # Se llenará abajo
                })

            # 6. Ordenar
            final_scores.sort(key=lambda x: x['score_combinado'], reverse=True)
            top_results = final_scores[:top_k]

            # 7. Generar Explicaciones con SHAP Real
            # Preparamos datos para el modelo de explicación
            training_data = []
            for result in top_results:
                evidencias = result['evidencias']
                training_data.append({
                    'entidades_match_count': len(evidencias.get('entidades_clave', [])),
                    'history_score': result['score_historico'],
                    'semantic_score': result['score_semantico'], # ADDED: Crucial for SHAP to explain the score
                    'target': result['score_combinado']
                })

            # Entrenar modelo explicativo (overfitting intencional para explicar la fórmula actual)
            if training_data:
                self.explanation_model.train(training_data)
                
                # Generar explicaciones
                df_predict = pd.DataFrame(training_data)
                shap_values_list = self.explanation_model.explain(df_predict)
            else:
                shap_values_list = [{}] * len(top_results)

            recommendations_to_save = []
            recommendations_for_api = []
            
            for idx, result in enumerate(top_results):
                shap_expl = shap_values_list[idx] if idx < len(shap_values_list) else {}
                
                # Mapear nombres de features a nombres amigables si es necesario
                # (El frontend espera claves específicas, ajustamos si hace falta)
                
                docente = result['docente_obj']
                rec_data = {
                    'docente_id': docente.id,
                    'nombre': docente.nombre,
                    'email': docente.email,
                    'grado': docente.grado,
                    'entidades_clave': docente.entidades_clave,
                    'score_combinado': round(result['score_combinado'] * 100, 2),
                    'score_historico': round(result['score_historico'] * 100, 2),
                    'score_semantico': round(result['score_semantico'] * 100, 2),
                    'evidencias': result['evidencias'],
                    'shap_explanations': shap_expl,
                    'from_cache': False
                }
                
                recommendations_for_api.append(rec_data)
                recommendations_to_save.append(rec_data)

            # 8. Guardar en Cache
            if use_cache:
                crud.save_recomendaciones_cache(
                    db, curso_id, recommendations_to_save, version_algoritmo="sbert_v2.0_veteran"
                )

            return recommendations_for_api

        except Exception as e:
            import traceback
            logger.error(f"Error al generar recomendaciones para el curso {curso_id}: {e}")
            traceback.print_exc()
            return []

recommendation_engine = RecommendationEngine()