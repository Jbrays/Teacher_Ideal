import asyncio
import logging
import os
import re
import unicodedata
from typing import Any, Coroutine, List

logger = logging.getLogger(__name__)

_fast_sbert_model = None


def get_fast_sbert_model():
  global _fast_sbert_model
  if _fast_sbert_model is None:
    if "HF_HOME" not in os.environ:
      os.environ["HF_HOME"] = "/app/.cache/huggingface"
      os.environ["SENTENCE_TRANSFORMERS_HOME"] = "/app/.cache/sbert"
      os.environ["HF_HUB_OFFLINE"] = "1"
      os.environ["TRANSFORMERS_OFFLINE"] = "1"

    try:
      from sentence_transformers import SentenceTransformer
      logger.info("Cargando modelo SBERT rápido jaimevera1107/all-MiniLM-L6-v2-similarity-es para validación...")
      _fast_sbert_model = SentenceTransformer('jaimevera1107/all-MiniLM-L6-v2-similarity-es')
      logger.info("Modelo jaimevera1107/all-MiniLM-L6-v2-similarity-es cargado exitosamente.")
    except Exception as e:
      logger.error(f"Error cargando jaimevera1107/all-MiniLM-L6-v2-similarity-es: {e}", exc_info=True)
  return _fast_sbert_model


def normalizar_texto(s: str) -> str:
  if not s:
    return ""
  s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')
  return re.sub(r'\s+', ' ', s.strip()).lower()


def quitar_etiqueta_inferido(entidad: str) -> str:
  return re.sub(r'\s*\(inferido\)\s*', '', entidad, flags=re.IGNORECASE).strip()


# Lista corta de patrones y carreras que NUNCA deben ser entidades.
_PATRONES_INVALIDOS = [
  r'maestri?a en', r'master en', r'magister en', r'm\.sc\.? en', r'msc en',
  r'doctor en', r'doctorado en', r'ph\.?d\.? en',
  r'bachiller en', r'licenciatura en', r'lic\.? en',
  r'(?:^|\s)ingenieri?a (?:de|en|industrial|de sistemas|de software|informatica|de computacion)(?:\s|$)',
  r'sistemas de informacion',
  r'ciencias de la computacion',
  r'computacion e informatica',
  r'administracion$', r'contabilidad$', r'economia$', r'derecho$', r'medicina$',
]

_CARRERAS_COMUNES = [
  "sistemas de informacion",
  "ingenieria de software",
  "ingenieria de sistemas",
  "ingenieria industrial",
  "ingenieria informatica",
  "ingenieria de computacion",
  "ciencias de la computacion",
  "computacion e informatica",
  "administracion",
  "contabilidad",
  "economia",
  "derecho",
  "medicina",
  "educacion",
  "pedagogia",
]

_CONCEPTOS_PROHIBIDOS = [
  "nombre de carrera universitaria",
  "titulo academico",
  "grado academico",
  "institucion educativa",
  "universidad o instituto",
  "cargo administrativo",
  "puesto de trabajo",
  "rol laboral",
]


def es_entidad_invalida_por_patron(entidad: str) -> bool:
  texto = normalizar_texto(entidad)
  if not texto:
    return True

  for patron in _PATRONES_INVALIDOS:
    if re.search(patron, texto):
      return True

  for carrera in _CARRERAS_COMUNES:
    if carrera in texto or texto in carrera:
      return True

  if any(p in texto for p in ["universidad ", "instituto ", "escuela ", "facultad ", "colegio "]):
    return True

  if any(texto.startswith(p) for p in [
    "gerente ", "jefe ", "director ", "superintendente ", "apoderado ",
    "asistente ", "analista ", "consultor ", "asesor ", "coordinador ",
    "encargado ", "presidente ", "miembro ", "profesor ", "docente "
  ]):
    return True

  return False


def filtrar_por_similitud_semantica(entidades: List[str], umbral: float = 0.72) -> List[str]:
  model = get_fast_sbert_model()
  if not model or not entidades:
    return entidades

  try:
    from sklearn.metrics.pairwise import cosine_similarity

    entidades_limpias = [quitar_etiqueta_inferido(e) for e in entidades]
    ent_vecs = model.encode(entidades_limpias, convert_to_numpy=True)
    prohib_vecs = model.encode(_CONCEPTOS_PROHIBIDOS, convert_to_numpy=True)

    if ent_vecs.ndim == 1:
      ent_vecs = ent_vecs.reshape(1, -1)

    sim_matrix = cosine_similarity(ent_vecs, prohib_vecs)
    max_sims = sim_matrix.max(axis=1)

    validadas = []
    for entidad, sim in zip(entidades, max_sims):
      if float(sim) >= umbral:
        logger.warning(f" Entidad descartada por similitud semántica ({sim:.2f}): '{entidad}'")
        continue
      validadas.append(entidad)

    return validadas
  except Exception as e:
    logger.error(f"Error en filtro semántico: {e}", exc_info=True)
    return entidades


def entidad_aparece_en_texto(entidad: str, texto: str, umbral: float = 0.72) -> bool:
  if not entidad or not texto:
    return False

  texto_normalizado = normalizar_texto(texto)
  entidad_limpia = quitar_etiqueta_inferido(entidad)

  if normalizar_texto(entidad_limpia) in texto_normalizado:
    return True

  palabras = [p for p in normalizar_texto(entidad_limpia).split() if len(p) > 3]
  if palabras and all(p in texto_normalizado for p in palabras):
    return True

  model = get_fast_sbert_model()
  if not model:
    return True

  try:
    from sklearn.metrics.pairwise import cosine_similarity

    frases = [f.strip() for f in re.split(r'[.\n]', texto) if len(f.strip()) > 15]
    if not frases:
      return True

    ent_vec = model.encode([entidad_limpia], convert_to_numpy=True)
    frase_vecs = model.encode(frases, convert_to_numpy=True)

    if frase_vecs.ndim == 1:
      frase_vecs = frase_vecs.reshape(1, -1)

    sim_matrix = cosine_similarity(ent_vec, frase_vecs)
    max_sim = float(sim_matrix.max())

    return max_sim >= umbral
  except Exception as e:
    logger.error(f"Error verificando entidad contra texto: {e}", exc_info=True)
    return True


def limpiar_entidades(
  entidades: List[str],
  texto: str,
  min_entidades: int = 3,
  max_entidades: int = 6
) -> List[str]:
  if not entidades:
    return ["[No declarado]"]

  vistas = set()
  unicas = []
  for e in entidades:
    limpia = e.strip()
    if not limpia:
      continue
    key = normalizar_texto(quitar_etiqueta_inferido(limpia))
    if key and key not in vistas:
      vistas.add(key)
      unicas.append(limpia)

  filtradas = []
  for e in unicas:
    if es_entidad_invalida_por_patron(e):
      logger.warning(f" Entidad descartada por patrón: '{e}'")
      continue
    filtradas.append(e)

  filtradas = filtrar_por_similitud_semantica(filtradas)

  respaldadas = []
  for e in filtradas:
    if entidad_aparece_en_texto(e, texto):
      respaldadas.append(e)
    else:
      logger.warning(f" Entidad descartada por no aparecer en texto: '{e}'")

  if len(respaldadas) < min_entidades:
    logger.warning(f" Solo {len(respaldadas)} entidades respaldadas. Se devuelven todas, pero puede requerirse reintento.")
    return respaldadas if respaldadas else ["[No declarado]"]

  if len(respaldadas) > max_entidades:
    logger.info(f" Se truncan entidades de {len(respaldadas)} a {max_entidades}.")
    return respaldadas[:max_entidades]

  return respaldadas


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
  """
  Ejecuta una coroutine de forma segura tanto si hay un event loop activo
  como si no. Útil para llamar código async desde funciones síncronas.
  """
  try:
    return asyncio.run(coro)
  except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
      return loop.run_until_complete(coro)
    finally:
      loop.close()
