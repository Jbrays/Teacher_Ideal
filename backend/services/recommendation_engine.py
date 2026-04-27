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

# Cargar modelo SBERT
try:
    model = SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')
except Exception:
    model = None

class RecommendationEngine:
    def __init__(self):
        self.model = model
        self.explanation_model = ExplanationModel()

    def _create_profile_text(self, *, areas, lenguajes, herramientas, metodologias, contenidos=None, descripcion="", texto_adicional="") -> str:
        parts = []
        if descripcion:
            parts.append(f"Descripción: {descripcion}")
        if texto_adicional:
            parts.append(f"Contexto general: {texto_adicional[:3000]}")
        
        entity_text = []
        if areas:
            entity_text.append(f"Áreas de especialización: {', '.join(areas)}.")
        if lenguajes:
            entity_text.append(f"Lenguajes de programación: {', '.join(lenguajes)}.")
        if herramientas:
            entity_text.append(f"Herramientas y tecnologías: {', '.join(herramientas)}.")
        if metodologias:
            entity_text.append(f"Metodologías: {', '.join(metodologias)}.")
        if contenidos:
            entity_text.append(f"Contenidos temáticos: {', '.join(contenidos)}.")
            
        if entity_text:
            profile = " ".join(entity_text)
            parts.append(f"Perfil principal: {profile}")
            parts.append(f"Competencias: {profile}")
            
        return " ".join(parts)

    def create_curso_text(self, curso: Curso) -> str:
        nombre_curso = f"Curso: {curso.nombre}. " * 3
        # Verificar si el modelo tiene 'contenidos', si no, usar lista vacía
        contenidos = curso.contenidos if hasattr(curso, 'contenidos') else []
        
        profile = self._create_profile_text(
            areas=curso.areas,
            lenguajes=curso.lenguajes,
            herramientas=curso.herramientas,
            metodologias=curso.metodologias,
            contenidos=contenidos,
            descripcion=curso.descripcion
        )
        return nombre_curso + profile

    def create_docente_text(self, docente: Docente) -> str:
        # Verificar si el modelo tiene 'contenidos', si no, usar lista vacía
        contenidos = docente.contenidos if hasattr(docente, 'contenidos') else []
        
        return self._create_profile_text(
            areas=docente.areas,
            lenguajes=docente.lenguajes,
            herramientas=docente.herramientas,
            metodologias=docente.metodologias,
            contenidos=contenidos,
            texto_adicional=docente.cv_text
        )

    def _calculate_ner_evidencias(self, curso: Curso, docente: Docente) -> Dict:
        curso_contenidos = getattr(curso, 'contenidos', []) or []
        docente_contenidos = getattr(docente, 'contenidos', []) or []
        return {
            "areas": list(set(curso.areas).intersection(set(docente.areas))),
            "lenguajes": list(set(curso.lenguajes).intersection(set(docente.lenguajes))),
            "herramientas": list(set(curso.herramientas).intersection(set(docente.herramientas))),
            "metodologias": list(set(curso.metodologias).intersection(set(docente.metodologias))),
            "contenidos": list(set(curso_contenidos).intersection(set(docente_contenidos))),
        }

    def get_embedding_for_text(self, text: str) -> np.ndarray:
        if not self.model:
            raise Exception("Modelo SBERT no cargado")
        return self.model.encode([text], convert_to_numpy=True)[0].reshape(1, -1)

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
                            'areas': docente.areas,
                            'herramientas': docente.herramientas,
                            'lenguajes': docente.lenguajes,
                            'metodologias': docente.metodologias,
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
                    'area_match_count': len(evidencias.get('areas', [])),
                    'lenguaje_match_count': len(evidencias.get('lenguajes', [])),
                    'herramienta_match_count': len(evidencias.get('herramientas', [])),
                    'metodologia_match_count': len(evidencias.get('metodologias', [])),
                    'contenido_match_count': len(evidencias.get('contenidos', [])),
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
                    'areas': docente.areas,
                    'herramientas': docente.herramientas,
                    'lenguajes': docente.lenguajes,
                    'metodologias': docente.metodologias,
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
            print(f"Error al generar recomendaciones para el curso {curso_id}: {e}")
            traceback.print_exc()
            return []

recommendation_engine = RecommendationEngine()