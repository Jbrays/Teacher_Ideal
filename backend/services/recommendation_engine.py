from typing import List, Dict
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import vertexai
from vertexai.generative_models import GenerativeModel
from sqlalchemy.orm import Session
from backend.services.embeddings_manager import embeddings_manager
from backend.database import crud
from backend.database.models import Curso, Docente

import logging
import os

logger = logging.getLogger(__name__)

# Forzar a HuggingFace a usar SOLO el modelo pre-horneado en Docker
os.environ["HF_HUB_OFFLINE"] = "1"

# Variable global para lazy loading
_sbert_model = None

def get_sbert_model():
    global _sbert_model
    if _sbert_model is None:
        logger.info("Cargando modelo SBERT BAAI/bge-m3 a memoria por primera vez...")
        try:
            _sbert_model = SentenceTransformer('BAAI/bge-m3')
            _sbert_model.half()
            logger.info("Modelo SBERT cargado exitosamente.")
        except Exception as e:
            logger.error(f"Error cargando SBERT: {e}")
    return _sbert_model


class RecommendationEngine:
    def __init__(self):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        self.model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-3.1-flash-lite")
        try:
            vertexai.init(project=self.project_id, location=self.location)
            self.gemini_model = GenerativeModel(self.model_name)
        except Exception as e:
            logger.error(f"Error iniciando Vertex AI para NLG: {e}")
            self.gemini_model = None

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

    def _generate_nlg_explanation(self, curso_text: str, docente_text: str) -> str:
        if not self.gemini_model:
            return "Motivos de elección:\n* El docente posee un perfil semántico que coincide con los requerimientos del curso."
            
        prompt = f"""
        Actúa como un experto en auditoría de talento docente. El sistema ha seleccionado a un docente basándose en una coincidencia semántica técnica. Tu tarea es extraer la evidencia concreta de ese match.
        
        REGLAS DE REDACCIÓN ESTRICTAS:
        1. Cero Etiquetas: NO menciones "Matches Explícitos", "Matches Latentes", "Sugerencia", "Sugerencia de Gemini" ni ningún título interno.
        2. Cero Marca: NO menciones "Gemini", "XAI", "BGE" ni "Similitud".
        3. Formato Directo: Tu respuesta DEBE empezar con el título: "Motivos de elección:" seguido de una lista de bullets (*).
        4. Contenido de los Bullets: Cada punto debe ser una frase corta (máx. 15 palabras) que describa una coincidencia técnica o un valor agregado profesional. Formato sugerido: Bullet -> Habilidad/Logro -> Relación con el curso.
        5. Evidencia, no Excusas: No intentes "justificar" el match; simplemente lista los hechos encontrados en el CV que se alinean con el curso. Si el docente tiene una trayectoria superior (ej. NASA), lístalo como valor agregado.
        
        SÍLABO: {curso_text[:3000]}
        CV DOCENTE: {docente_text[:3000]}
        """
        try:
            response = self.gemini_model.generate_content(
                prompt,
                generation_config={"temperature": 0.2, "max_output_tokens": 512}
            )
            text = response.text.strip()
            if not text.startswith("Motivos"):
                text = "Motivos de elección:\n" + text
            return text
        except Exception as e:
            logger.error(f"Error generando explicación NLG: {e}")
            return "Motivos de elección:\n* Perfil técnico alineado con las competencias de la materia."

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
                            'score_historico': round(cache_entry.score_historico * 100, 2),
                            'score_semantico': round(cache_entry.score_semantico * 100, 2),
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

            # --- LÓGICA DE ASHP: HISTORIAL Y P_SAT ---
            historial = crud.get_historial_by_curso(db, curso_id)
            
            # Obtener todos los periodos cronológicos en los que se dictó el curso
            all_course_periods = sorted(list(set(h.periodo for h in historial)), reverse=True)
            
            # Agrupar historial por docente
            docente_history = {}
            for h in historial:
                if h.docente_id not in docente_history:
                    docente_history[h.docente_id] = []
                docente_history[h.docente_id].append(h.periodo)
            
            VETERAN_THRESHOLD = 8 
            W_SEM = 0.7
            W_HIST = 0.3

            def calculate_p_sat(docente_periods: List[str]) -> float:
                """Calcula el factor de penalización por saturación de semestres consecutivos."""
                if not all_course_periods or not docente_periods:
                    return 1.0
                
                # Contar cuántas veces seguidas dictó el curso contando desde el último periodo ofrecido
                consecutive_count = 0
                for period in all_course_periods:
                    if period in docente_periods:
                        consecutive_count += 1
                    else:
                        break
                        
                if consecutive_count >= 3:
                    return 0.5
                elif consecutive_count == 2:
                    return 0.8
                return 1.0

            # 3. Obtener Embeddings
            curso_text = self.create_curso_text(curso)
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

            # 4. Calcular Similitud Semántica (S_BGE)
            similarities = cosine_similarity(curso_embedding, docentes_vectors)[0]

            # 5. Calcular Score Final (ASHP)
            final_scores = []
            for idx, docente_id in enumerate(docente_ids):
                docente = crud.get_docente_by_id(db, docente_id)
                if not docente: continue
                
                s_bge = float(similarities[idx])
                
                # Historial y P_sat
                d_periods = docente_history.get(docente_id, [])
                semesters_taught = len(d_periods)
                s_hist = min(semesters_taught / VETERAN_THRESHOLD, 1.0)
                p_sat = calculate_p_sat(d_periods)
                
                combined_score = (s_bge * W_SEM) + (s_hist * p_sat * W_HIST)
                
                evidencias = self._calculate_ner_evidencias(curso, docente)
                
                final_scores.append({
                    'docente_id': docente.id,
                    'docente_obj': docente,
                    'score_combinado': combined_score,
                    'score_historico': s_hist,
                    'score_semantico': s_bge,
                    'p_sat': p_sat,
                    'evidencias': evidencias
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
            for idx, result in enumerate(top_results):
                docente = result['docente_obj']
                
                # XAI NLG (Traducción)
                xai_text = ""
                if idx < 3: # Limitar a los mejores
                    docente_text = self.create_docente_text(docente)
                    xai_text = self._generate_nlg_explanation(curso_text, docente_text)
                
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
                    'score_historico': round(result['score_historico'] * 100, 2),
                    'score_semantico': round(result['score_semantico'] * 100, 2),
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
                crud.save_recomendaciones_cache(
                    db, curso_id, recommendations_to_save, version_algoritmo="ashp_v1.0"
                )

            return recommendations_for_api

        except Exception as e:
            import traceback
            logger.error(f"Error al generar recomendaciones para el curso {curso_id}: {e}")
            traceback.print_exc()
            return []

recommendation_engine = RecommendationEngine()