import spacy
import logging
from spacy.pipeline import EntityRuler
from typing import Dict, List, Optional

# Configuración de Logging
logger = logging.getLogger(__name__)

# Intentamos importar las listas de palabras clave
# Si falla, definimos listas vacías para que el servicio no se caiga
try:
    from .ner_keywords import (
        PATTERNS_AREAS,
        PATTERNS_LENGUAJES,
        PATTERNS_HERRAMIENTAS,
        PATTERNS_METODOLOGIAS,
        PATTERNS_CONTENIDOS
    )
except ImportError:
    logger.warning("No se encontró 'ner_keywords.py' o faltan variables. El NER funcionará sin patrones personalizados.")
    PATTERNS_AREAS = []
    PATTERNS_LENGUAJES = []
    PATTERNS_HERRAMIENTAS = []
    PATTERNS_METODOLOGIAS = []
    PATTERNS_CONTENIDOS = []

def load_spacy_model():
    """
    Carga el modelo de spaCy 'es_core_news_lg' y añade el EntityRuler 
    para detectar habilidades técnicas específicas.
    """
    try:
        # Cargamos el modelo grande de español
        # disable=["parser"] opcional si no necesitas análisis sintáctico (hace la carga más rápida)
        nlp = spacy.load("es_core_news_lg")
        
        # Aumentamos el límite de caracteres una sola vez al cargar
        nlp.max_length = 2000000 
        
        # Añadimos el EntityRuler ANTES del NER estándar para dar prioridad a nuestras listas
        ruler = nlp.add_pipe("entity_ruler", before="ner")

        patterns = []

        def create_case_insensitive_pattern(term: str, label: str) -> Dict:
            """
            Crea un patrón de spaCy que ignora mayúsculas/minúsculas.
            Divide términos de varias palabras en tokens individuales.
            """
            words = term.split(' ')
            pattern_list = [{"LOWER": word.lower()} for word in words]
            return {"label": label, "pattern": pattern_list}

        # Cargar patrones de forma segura
        for term in PATTERNS_AREAS: patterns.append(create_case_insensitive_pattern(term, "AREA"))
        for term in PATTERNS_LENGUAJES: patterns.append(create_case_insensitive_pattern(term, "LENGUAJE"))
        for term in PATTERNS_HERRAMIENTAS: patterns.append(create_case_insensitive_pattern(term, "HERRAMIENTA"))
        for term in PATTERNS_METODOLOGIAS: patterns.append(create_case_insensitive_pattern(term, "METODOLOGIA"))
        for term in PATTERNS_CONTENIDOS: patterns.append(create_case_insensitive_pattern(term, "CONTENIDO"))
            
        if patterns:
            ruler.add_patterns(patterns)
            logger.info(f"Modelo NLP cargado con {len(patterns)} patrones personalizados.")
        else:
            logger.info("ℹModelo NLP cargado sin patrones personalizados (listas vacías).")
            
        return nlp
        
    except OSError:
        logger.error("Error: No se encontró el modelo 'es_core_news_lg'.")
        logger.info("ℹEjecuta: python -m spacy download es_core_news_lg")
        return None
    except Exception as e:
        logger.critical(f"Error inesperado cargando NLP: {e}")
        return None

# --- INSTANCIA GLOBAL ---
nlp = load_spacy_model()

def normalize_term(term: str, label: str) -> str:
    """Normaliza mayúsculas/minúsculas basándose en listas comunes de TI."""
    term = term.strip().title() # Por defecto Title Case (Machine Learning)
    
    # Conjunto de acrónimos que deben ir en mayúsculas
    # Usamos un set para búsqueda O(1)
    acronimos = {
        'Sql', 'Php', 'Html', 'Css', 'Aws', 'Api', 'Net', 'J2ee', 'Pl/Sql', 'Dba',
        'Json', 'Xml', 'Rest', 'Jwt', 'Soap', 'Mvc', 'Orm', 'Saas', 'Paas', 'Iaas',
        'Erp', 'Crm', 'Sap', 'Uml', 'Http', 'Tcp', 'Ip'
    }
    
    if term in acronimos:
        return term.upper()
    
    # Casos especiales manuales
    if term == 'Dotnet' or term == '.Net': return '.NET'
    if term.lower() == 'c#': return 'C#'
    if term.lower() == 'c++': return 'C++'
    if term.lower() == 'nodejs': return 'Node.js'
    if term.lower() == 'reactjs': return 'React'
    if term.lower() == 'vuejs': return 'Vue.js'
    
    return term

def extract_entities(text: str) -> Dict[str, List[str]]:
    """
    Extrae habilidades técnicas del texto, las normaliza y elimina duplicados.
    """
    results = {
        'areas': [],
        'lenguajes': [],
        'herramientas': [],
        'metodologias': [],
        'contenidos': []
    }

    if not nlp or not text:
        return results

    try:
        doc = nlp(text)
        
        # Usamos Sets para eliminar duplicados automáticamente
        areas = set()
        lenguajes = set()
        herramientas = set()
        metodologias = set()
        contenidos = set()
        
        for ent in doc.ents:
            # Normalización inteligente
            term = normalize_term(ent.text, ent.label_)
            
            # Filtro de ruido:
            # Permitimos términos de 1 letra SOLO si son Lenguajes (ej: "C", "R")
            if len(term) < 2 and ent.label_ != "LENGUAJE":
                continue

            if ent.label_ == "AREA":
                areas.add(term)
            elif ent.label_ == "LENGUAJE":
                lenguajes.add(term)
            elif ent.label_ == "HERRAMIENTA":
                herramientas.add(term)
            elif ent.label_ == "METODOLOGIA":
                metodologias.add(term)
            elif ent.label_ == "CONTENIDO":
                contenidos.add(term)
        
        # Convertimos a listas ordenadas para la respuesta JSON
        results['areas'] = sorted(list(areas))
        results['lenguajes'] = sorted(list(lenguajes))
        results['herramientas'] = sorted(list(herramientas))
        results['metodologias'] = sorted(list(metodologias))
        results['contenidos'] = sorted(list(contenidos))
        
        return results

    except Exception as e:
        logger.error(f"⚠️ Error extrayendo entidades: {e}")
        return results