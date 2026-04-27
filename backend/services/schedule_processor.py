import re
import logging
import pdfplumber
from io import BytesIO
import os
import json
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session

# Vertex AI Imports
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from google.oauth2 import service_account

# Configuración de Logging 
logger = logging.getLogger(__name__)

# Intentamos importar los modelos. 
# Usamos un bloque try para que el procesador no rompa la app si falla la importación al inicio.
try:
    from backend.database.models import Historial, Docente, Curso
    from sentence_transformers import SentenceTransformer, util
except ImportError:
    logger.critical("Error crítico: No se pudieron importar los modelos de BD (Historial, Docente, Curso) o SentenceTransformer.")
    Historial, Docente, Curso = None, None, None
    SentenceTransformer, util = None, None

class ScheduleProcessor:
    """
    Procesa PDFs de horarios académicos de la UPAO.
    Optimizado para evitar consultas N+1 a la base de datos.
    """

    def __init__(self):
        # Configuración de Vertex AI
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        self.model_name = "gemini-2.0-flash-001"
        
        try:
            vertexai.init(project=self.project_id, location=self.location)
            self.model = GenerativeModel(self.model_name)
            logger.info(f"Vertex AI inicializado correctamente con modelo: {self.model_name}")
        except Exception as e:
            logger.error(f"Error inicializando Vertex AI: {e}")
            self.model = None

    def _extract_periodo_from_filename(self, filename: str) -> str:
        """Intenta extraer el periodo del nombre del archivo (ej: 2024-10)."""
        # Soporta: 2024-10, 2024 10, 202410, 2024-1, 2024 1
        # FIX: Restringir ciclo a 10 o 20 (evita confundir con fechas como 2024-08)
        match = re.search(r'(20\d{2})[-_\s]?(10|20)', filename)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
        return None # Retornamos None para indicar fallo

    def _extract_periodo_from_text(self, text: str) -> str:
        """Busca patrones de periodo en el texto del encabezado."""
        # Patrones comunes en encabezados: "SEMESTRE 2024-10", "CICLO 2024 20", "2024-I", "2024-II"
        
        # 1. Formato numérico estándar: 2024-10, 2024 20, 202410
        # FIX: Restringir ciclo a 10 o 20
        match_num = re.search(r'(20\d{2})[-_\s]?(10|20)', text)
        if match_num:
            return f"{match_num.group(1)}-{match_num.group(2)}"
            
        # 2. Formato Romano: 2024-I, 2024-II, 2024 I, 2024 II
        match_roman = re.search(r'(20\d{2})[-_\s]?(I{1,2})', text, re.IGNORECASE)
        if match_roman:
            year = match_roman.group(1)
            cycle_roman = match_roman.group(2).upper()
            cycle = "10" if cycle_roman == "I" else "20"
            return f"{year}-{cycle}"
            
        return "HISTORICO"

    def extract_schedule_data(self, pdf_path: str) -> List[Dict]:
        """
        Extrae la información del horario usando Vertex AI (Gemini) por lotes de páginas.
        Optimización: Procesa 3 páginas por request para reducir tiempo y llamadas API.
        """
        if not self.model:
            logger.error("❌ Modelo Vertex AI no disponible.")
            return []

        filename = os.path.basename(pdf_path)
        logger.info(f"🚀 Procesando horario con Vertex AI (Batching): {filename}")
        all_results = []
        
        try:
            import time
            
            # 1. Determinar Periodo Global
            # Estrategia A: Nombre del archivo
            global_period = self._extract_periodo_from_filename(filename)
            
            with pdfplumber.open(pdf_path) as pdf:
                # Estrategia B: Si falla nombre, buscar en primera página
                if not global_period:
                    logger.info("⚠️ Periodo no encontrado en nombre de archivo. Buscando en contenido...")
                    if len(pdf.pages) > 0:
                        first_page_text = pdf.pages[0].extract_text() or ""
                        global_period = self._extract_periodo_from_text(first_page_text)
                    else:
                        global_period = "HISTORICO"
                
                logger.info(f"📅 Periodo Global detectado: {global_period}")

                total_pages = len(pdf.pages)
                batch_size = 5 # Aumentado a 5 para reducir llamadas API
                
                print(f"📄 Total páginas: {total_pages} | Batch Size: {batch_size}")
                
                for i in range(0, total_pages, batch_size):
                    # Construir lote
                    batch_pages = pdf.pages[i : i + batch_size]
                    batch_text = ""
                    for idx, page in enumerate(batch_pages):
                        text = page.extract_text(layout=True) or ""
                        batch_text += f"\n--- PÁGINA {i + idx + 1} ---\n{text}\n"
                    
                    print(f"   ⏳ Procesando Batch {i//batch_size + 1}/{(total_pages + batch_size - 1)//batch_size} (Págs {i+1}-{min(i+batch_size, total_pages)})...")
                    
                    prompt = f"""
                    Analiza este TEXTO extraído de varias páginas de un horario universitario.
                    Extrae TODAS las asignaciones de cursos a docentes.
                    
                    TEXTO DEL LOTE:
                    {batch_text}
                    
                    Reglas:
                    1. Ignora "STAFF" o "DOCENTE" genérico.
                    2. Extrae CÓDIGO (ej: "ICSI424") y NOMBRE del curso.
                    3. Extrae NOMBRE del docente.
                    4. IGNORA el periodo del texto, usaremos uno global.
                    
                    Salida JSON (Lista de objetos):
                    [
                        {{"curso_codigo": "ICSI424", "curso_nombre": "GESTION...", "docente_nombre": "JUAN PEREZ"}}
                    ]
                    """
                    
                    # RETRY LOGIC PARA VERTEX AI (429, 503 & JSON Errors)
                    import random
                    max_retries = 5 # Aumentado a 5 intentos
                    for attempt in range(max_retries):
                        try:
                            # Rate limiting preventivo con Jitter
                            base_wait = (attempt + 1) * 5
                            jitter = random.uniform(0, 3)
                            if attempt > 0: time.sleep(base_wait + jitter)
                            else: time.sleep(2)

                            response = self.model.generate_content(
                                prompt,
                                generation_config={
                                    "response_mime_type": "application/json",
                                    "temperature": 0.1,
                                    "max_output_tokens": 8192
                                }
                            )
                            
                            json_text = response.text.replace("```json", "").replace("```", "").strip()
                            data = json.loads(json_text)
                            
                            if isinstance(data, dict):
                                if "asignaciones" in data: data = data["asignaciones"]
                                else: data = [data]
                                
                            # Procesar y limpiar datos del lote
                            for d in data:
                                if not d.get('docente_nombre') or not d.get('curso_nombre'):
                                    continue
                                
                                # FORZAR PERIODO GLOBAL
                                d['periodo'] = global_period
                                all_results.append(d)
                            
                            break # Éxito, salir del retry loop
                            
                        except Exception as e:
                            error_str = str(e)
                            is_503 = "503" in error_str or "Handshake read failed" in error_str or "FD Shutdown" in error_str or "Socket closed" in error_str
                            is_429 = "429" in error_str or "Resource exhausted" in error_str
                            
                            if is_429 or is_503:
                                # Backoff más agresivo para errores de conexión/quota
                                wait_time = (attempt + 1) * 15 + random.uniform(0, 5) # 15s, 30s, 45s...
                                err_type = "Quota (429)" if is_429 else "Connection (503)"
                                logger.warning(f"⚠️ {err_type} en Batch {i//batch_size + 1}. Reintentando en {wait_time:.1f}s... ({attempt+1}/{max_retries})")
                                time.sleep(wait_time)
                            elif "Unterminated string" in error_str or "Expecting value" in error_str:
                                logger.warning(f"⚠️ Error JSON en Batch {i//batch_size + 1}: {e}. Reintentando... ({attempt+1}/{max_retries})")
                            else:
                                logger.error(f"⚠️ Error en Batch {i//batch_size + 1}: {e}")
                                # Si no es recuperable, seguimos (o reintentamos si queda chance)
                                if attempt == max_retries - 1: pass

            logger.info(f"✅ Vertex AI extrajo {len(all_results)} registros totales.")
            return all_results

        except Exception as e:
            logger.error(f"❌ Error procesando PDF con Vertex AI: {e}")
            return []

    def save_history_to_db(self, db: Session, data: List[Dict]) -> int:
        """
        Guarda los datos y actualiza el historial.
        OPTIMIZACIÓN: Carga todos los docentes y cursos en memoria una sola vez
        para evitar consultas repetitivas dentro del bucle.
        """
        if not data:
            return 0
            
        count = 0
        
        try:
            # --- 1. PRE-FETCHING (Optimización Clave) ---
            logger.info("⏳ Precargando catálogo de docentes y cursos para comparación rápida...")
            all_docentes = db.query(Docente).all()
            all_cursos = db.query(Curso).all()
            
            # Convertimos a listas de diccionarios con nombres normalizados para búsqueda rápida
            # Esto evita recalcular la normalización en cada iteración del bucle principal
            docentes_cache = [(d, self._normalize_docente_name(d.nombre)) for d in all_docentes]
            cursos_cache = [(c, self._normalize_curso_name(c.nombre)) for c in all_cursos]
            
            logger.info(f"📚 Catálogo cargado: {len(docentes_cache)} docentes, {len(cursos_cache)} cursos.")

            historial_entries = [] # Inicializar lista

            # --- 2. PROCESAMIENTO Y AGREGACIÓN ---
            # Usamos un diccionario para agregar conteos en memoria antes de tocar la BD
            # Clave: (docente_id, curso_id, periodo) -> Valor: veces
            aggregated_entries = {}

            for item in data:
                # Buscar Docente en memoria
                docente = self._find_docente_in_memory(docentes_cache, item['docente_nombre'])
                if not docente: continue
                
                # Buscar Curso en memoria (pasamos código y nombre)
                curso = self._find_curso_in_memory(cursos_cache, item.get('curso_codigo'), item['curso_nombre'])
                if not curso: continue
                
                # Clave única para agregación
                key = (docente.id, curso.id, item['periodo'])
                
                if key in aggregated_entries:
                    aggregated_entries[key] += 1
                else:
                    aggregated_entries[key] = 1

                # Actualizar CV text (esto sí se puede hacer incrementalmente o al final)
                curso_str = f"Dictó la asignatura: {item['curso_nombre']} (Periodo: {item['periodo']})."
                if not docente.cv_text: docente.cv_text = ""
                if curso_str not in docente.cv_text:
                    docente.cv_text += f"\n- {curso_str}"
                    db.add(docente)

            # --- 3. GUARDADO EN BD ---
            for (doc_id, cur_id, per), veces_count in aggregated_entries.items():
                # Verificar si ya existe en BD para sumar
                existing = db.query(Historial).filter(
                    Historial.docente_id == doc_id,
                    Historial.curso_id == cur_id,
                    Historial.periodo == per
                ).first()
                
                if existing:
                    existing.veces += veces_count
                    # Actualizar ultima_vez
                    from datetime import datetime
                    existing.ultima_vez = datetime.utcnow()
                    db.add(existing)
                else:
                    new_entry = Historial(
                        docente_id=doc_id,
                        curso_id=cur_id,
                        periodo=per,
                        resultado="Asignado en Horario",
                        veces=veces_count
                    )
                    db.add(new_entry)
                    count += 1
            
            db.commit()
            logger.info(f"💾 Commit exitoso: {count} nuevos registros de historial insertados (con agregación).")
            return count

        except Exception as e:
            db.rollback()
            logger.error(f"❌ Error en transaccion de historial: {e}")
            return 0

    def _find_curso_in_memory(self, cursos_cache: List[Tuple[Curso, str]], codigo_buscado: str, nombre_buscado: str) -> Optional[Curso]:
        """Busca curso por código (prioridad) o nombre."""
        
        # 1. Búsqueda exacta por código (si existe)
        if codigo_buscado:
            # Normalizar código buscado: quitar espacios y guiones
            codigo_clean = codigo_buscado.replace(" ", "").replace("-", "").upper() 
            for curso_obj, _ in cursos_cache:
                if curso_obj.codigo:
                    # Normalizar código DB: quitar espacios y guiones
                    db_code_clean = curso_obj.codigo.replace(" ", "").replace("-", "").upper()
                    if db_code_clean == codigo_clean:
                        return curso_obj
        
        # 2. Búsqueda difusa por nombre
        nombre_clean = self._normalize_curso_name(nombre_buscado)
        best_match = None
        best_score = 0
        
        for curso_obj, curso_nombre_norm in cursos_cache:
            score = self._calculate_similarity(nombre_clean, curso_nombre_norm)
            if score > best_score:
                best_score = score
                best_match = curso_obj
        
        # DEBUG CURSO
        if best_score > 0.4:
             print(f"   ? Candidato Curso: '{best_match.nombre}' | Score: {best_score:.2f} | Buscado: '{nombre_clean}'")

        if best_score > 0.80: # Cursos requieren más precisión
            return best_match
            
        # 3. Fallback: Búsqueda Semántica (SBERT) para cursos que cambiaron de nombre
        # Solo si el score anterior fue muy bajo (evitar costo computacional si ya tenemos un candidato decente)
        if best_score < 0.5:
            # print(f"   🧠 Intentando Match Semántico para: '{nombre_clean}'")
            best_semantic_score = 0
            best_semantic_match = None
            
            # Optimización: Solo comparar con cursos que tengan al menos 1 palabra en común o longitud similar
            # (Para no comparar con todo el catálogo a fuerza bruta si es muy grande)
            
            model = self._get_sbert_model()
            if model:
                # Codificar el nombre buscado una sola vez
                query_embedding = model.encode(nombre_clean, convert_to_tensor=True)
                
                for curso_obj, curso_nombre_norm in cursos_cache:
                    # Calcular similitud coseno
                    target_embedding = model.encode(curso_nombre_norm, convert_to_tensor=True)
                    sem_score = float(util.cos_sim(query_embedding, target_embedding)[0][0])
                    
                    if sem_score > best_semantic_score:
                        best_semantic_score = sem_score
                        best_semantic_match = curso_obj
                
                if best_semantic_score > 0.82: # Umbral semántico AJUSTADO (era 0.65, subido a 0.82 para evitar falsos positivos)
                    print(f"   🧠 Match Semántico: '{best_semantic_match.nombre}' | Score: {best_semantic_score:.2f} | Buscado: '{nombre_clean}'")
                    return best_semantic_match

        return None

    def _find_docente_in_memory(self, docentes_cache: List[Tuple[Docente, str]], nombre_buscado: str) -> Optional[Docente]:
        """Busca docente en la lista precargada."""
        nombre_clean = self._normalize_docente_name(nombre_buscado)
        best_match = None
        best_score = 0
        
        # DEBUG: Imprimir qué estamos buscando
        # print(f"🔍 Buscando docente: '{nombre_buscado}' (Norm: '{nombre_clean}')")

        for docente_obj, docente_nombre_norm in docentes_cache:
            score = self._calculate_name_similarity(nombre_clean, docente_nombre_norm)
            
            if score > best_score:
                best_score = score
                best_match = docente_obj

        # DEBUG: Mostrar el mejor candidato encontrado y su score
        if best_score > 0.4: # Solo mostrar si hay algo remotamente parecido
            print(f"   ? Candidato: '{best_match.nombre}' | Score: {best_score:.2f} | Buscado: '{nombre_clean}'")

        # FIX: Bajamos el umbral de 0.75 a 0.50 para permitir coincidencias parciales
        # (ej: "Juan Perez" vs "Juan Carlos Perez" -> Score 0.66)
        # La seguridad la da _calculate_name_similarity que exige al menos 2 palabras coincidentes.
        if best_score >= 0.50:
            return best_match
        
        return None
    
    def _remove_accents(self, input_str: str) -> str:
        import unicodedata
        nfkd_form = unicodedata.normalize('NFKD', input_str)
        return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

    def _normalize_curso_name(self, nombre: str) -> str:
        if not nombre: return ""
        nombre = nombre.upper().strip()
        nombre = self._remove_accents(nombre) # FIX: Remove accents
        
        # Limpieza agresiva específica UPAO
        nombre = re.sub(r'MODALIDAD.*', '', nombre)
        nombre = re.sub(r'TOTAL.*', '', nombre)
        
        abreviaturas = {
            'SIST': 'SISTEMAS', 'INFORM': 'INFORMACION', 'GESTION': 'GESTION', 'GEST': 'GESTION',
            'ADMIN': 'ADMINISTRACION', 'ADM': 'ADMINISTRACION', 'DESARR': 'DESARROLLO', 'DESA': 'DESARROLLO',
            'APLIC': 'APLICACIONES', 'PROG': 'PROGRAMACION', 'PROGRAM': 'PROGRAMACION', 'PROGRA': 'PROGRAMACION',
            'ORGANIZ': 'ORGANIZACION', 'EMPRESAS': 'EMPRESARIAL', 'BASE': 'BASES', 'DATOS': 'DATOS',
            'REDES': 'REDES', 'COMPUT': 'COMPUTACION', 'COMPUTAC': 'COMPUTACION', 'DISPOSIT': 'DISPOSITIVOS',
            'MOVILES': 'MOVILES', 'INTELIG': 'INTELIGENTES', 'ESTRUCTURA': 'ESTRUCTURAS', 'ALGORITMOS': 'ALGORITMOS',
            'ARQUI': 'ARQUITECTURA', 'INTR': 'INTRODUCCION', 'INTROD': 'INTRODUCCION', 'TECN': 'TECNOLOGIA',
            'PROY': 'PROYECTOS', 'FOND': 'FUNDAMENTOS', 'FUND': 'FUNDAMENTOS', 'EVAL': 'EVALUACION',
            'FORM': 'FORMULACION', 'METODOS': 'METODOS', 'CUANTITAT': 'CUANTITATIVOS', 'NEGOCIOS': 'NEGOCIOS',
            'TALL': 'TALLER', 'INTEG': 'INTEGRACION', 'MEDIO': 'MEDIO', 'AMB': 'AMBIENTE',
            'SOST': 'SOSTENIBLE', 'SEG': 'SEGURIDAD', 'INF': 'INFORMACION', 'VIDEO': 'VIDEO',
            'JUEG': 'JUEGOS', 'WEB': 'WEB', 'SOPORTE': 'SOPORTE', 'DECISIONES': 'DECISIONES',
            'DECISION': 'DECISIONES'
        }
        
        # Regex \b para reemplazo seguro de palabras completas
        for abrev, completo in abreviaturas.items():
            nombre = re.sub(r'\b' + abrev + r'\b', completo, nombre)
        
        nombre = re.sub(r'[^\w\s]', ' ', nombre)
        return ' '.join(nombre.split())
    
    def _normalize_docente_name(self, nombre: str) -> str:
        if not nombre: return ""
        nombre = nombre.upper().strip()
        nombre = self._remove_accents(nombre) # FIX: Remove accents
        nombre = nombre.replace(',', ' ')
        nombre = re.sub(r'[^\w\s]', ' ', nombre)
        return ' '.join(nombre.split())
    
    def _calculate_similarity(self, str1: str, str2: str) -> float:
        words1 = set(str1.split())
        words2 = set(str2.split())
        if not words1 or not words2: return 0.0
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        return len(intersection) / len(union) if union else 0.0

    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        words1 = set(name1.split())
        words2 = set(name2.split())
        if not words1 or not words2: return 0.0
        intersection = words1.intersection(words2)
        if len(intersection) < 2: return 0.0
        union = words1.union(words2)
        jaccard = len(intersection) / len(union) if union else 0.0
        # Bonus pequeño si hay al menos 2 coincidencias (Nombre + Apellido)
        if len(intersection) >= 2: jaccard += 0.1
        return min(jaccard, 1.0)

    # --- SBERT MATCHING ---
    def _get_sbert_model(self):
        if not hasattr(self, 'sbert_model'):
            try:
                self.sbert_model = SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')
            except:
                self.sbert_model = None
        return self.sbert_model

    def _calculate_semantic_similarity(self, text1: str, text2: str) -> float:
        model = self._get_sbert_model()
        if not model: return 0.0
        emb1 = model.encode(text1, convert_to_tensor=True)
        emb2 = model.encode(text2, convert_to_tensor=True)
        return float(util.cos_sim(emb1, emb2)[0][0])

schedule_processor = ScheduleProcessor()