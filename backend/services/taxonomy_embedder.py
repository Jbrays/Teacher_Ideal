"""
Servicio de embeddings para la taxonomía compartida.

Precalcula y cachea embeddings de los nodos resolubles usando el modelo E5
multilingüe configurado. Soporta búsqueda de los nodos más cercanos
a un término dado, con instrucciones asimétricas para query (término crudo)
y passage (nodo de taxonomía).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from backend.taxonomy.models import Taxonomy, TaxonomyNode
from backend.taxonomy.catalog import get_taxonomy

logger = logging.getLogger(__name__)

# Configurar paths de cache si no están definidos. En desarrollo usamos un cache
# dentro del proyecto; en producción (Docker) se puede sobreescribir con HF_HOME.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_HF_HOME = str(_PROJECT_ROOT / ".cache" / "huggingface")
if "HF_HOME" not in os.environ:
  os.environ["HF_HOME"] = _DEFAULT_HF_HOME
if "SENTENCE_TRANSFORMERS_HOME" not in os.environ:
  os.environ["SENTENCE_TRANSFORMERS_HOME"] = os.environ.get("HF_HOME", _DEFAULT_HF_HOME)

MODEL_NAME = os.getenv("TAXONOMY_EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
# La dimensión se lee del modelo en runtime; no se fija aquí.

# multilingual-e5-small fue entrenado con estos prefijos para recuperación
# asimétrica. El formato "Instruct: ... Query: ..." pertenece a otros modelos
# E5 y degrada de forma severa los resultados de este modelo.
EMBEDDING_FORMAT_VERSION = "multilingual-e5-query-passage-v1"


class TaxonomyEmbedder:
  """
  Encapsula el modelo de embeddings y los vectores precalculados de la taxonomía.
  """

  def __init__(
    self,
    taxonomy: Optional[Taxonomy] = None,
    model_name: Optional[str] = None,
    cache_dir: Optional[str | Path] = None,
  ):
    self.taxonomy = taxonomy or get_taxonomy()
    self.model_name = model_name or MODEL_NAME
    if cache_dir is not None:
      self.cache_dir = Path(cache_dir)
    elif os.environ.get("TAXONOMY_CACHE_DIR"):
      self.cache_dir = Path(os.environ["TAXONOMY_CACHE_DIR"])
    else:
      # Cache persistente dentro del proyecto por defecto.
      project_root = Path(__file__).resolve().parents[2]
      self.cache_dir = project_root / ".cache" / "taxonomy_embeddings"
    self.cache_dir.mkdir(parents=True, exist_ok=True)

    self._model = None
    self._node_ids: List[str] = []
    self._node_vectors: Optional[np.ndarray] = None # shape: (n_nodes, dim)
    self._node_texts: Dict[str, str] = {}

  def _load_model(self):
    if self._model is None:
      try:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Cargando modelo de embeddings de taxonomía: {self.model_name}")
        self._model = SentenceTransformer(self.model_name)
        logger.info("Modelo cargado exitosamente.")
      except Exception as e:
        logger.error(f"Error cargando modelo {self.model_name}: {e}", exc_info=True)
        raise
    return self._model

  def _node_text(self, node: TaxonomyNode) -> str:
    """
    Texto que representa un nodo para ser embeddeado.
    Incluye el nombre, aliases y descripción si existen.
    """
    parts = [node.name]
    if node.aliases:
      parts.extend([a for a in node.aliases if a and a != node.name])
    if node.description:
      parts.append(node.description)
    # Añadir contexto del path para desambiguar conceptos genéricos.
    path = node.path(self.taxonomy)
    if len(path) > 1:
      path_names = " > ".join([n.name for n in path[:-1]])
      parts.append(f"Context: {path_names}")
    return " | ".join(dict.fromkeys(p.strip() for p in parts if p.strip()))

  def _taxonomy_hash(self) -> str:
    """Hash estable de la taxonomía para invalidar caché cuando cambie."""
    nodes = sorted(self.taxonomy.all_nodes(), key=lambda n: n.id)
    data = [
      {
        "id": n.id,
        "name": n.name,
        "aliases": sorted(n.aliases),
        "description": n.description or "",
        "kind": n.kind,
        "source_version": n.source_version or "",
        "embedding_enabled": n.embedding_enabled,
      }
      for n in nodes
    ]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

  def _cache_path(self) -> Path:
    safe_model = self.model_name.replace("/", "__")
    return self.cache_dir / (
      f"taxonomy_embeddings_{safe_model}_{EMBEDDING_FORMAT_VERSION}_"
      f"{self._taxonomy_hash()}.pkl"
    )

  def _save_cache(self):
    cache_path = self._cache_path()
    payload = {
      "node_ids": self._node_ids,
      "node_vectors": self._node_vectors,
      "node_texts": self._node_texts,
      "model_name": self.model_name,
      "format_version": EMBEDDING_FORMAT_VERSION,
      "taxonomy_hash": self._taxonomy_hash(),
    }
    with open(cache_path, "wb") as f:
      pickle.dump(payload, f)
    logger.info(f"Embeddings de taxonomía cacheados en: {cache_path}")

  def _load_cache(self) -> bool:
    cache_path = self._cache_path()
    if not cache_path.exists():
      return False
    try:
      with open(cache_path, "rb") as f:
        payload = pickle.load(f)
      if payload.get("taxonomy_hash") != self._taxonomy_hash():
        return False
      if payload.get("format_version") != EMBEDDING_FORMAT_VERSION:
        return False
      self._node_ids = payload["node_ids"]
      self._node_vectors = payload["node_vectors"]
      self._node_texts = payload["node_texts"]
      logger.info(f"Embeddings de taxonomía cargados desde caché: {cache_path}")
      return True
    except Exception as e:
      logger.warning(f"No se pudo cargar caché de embeddings: {e}")
      return False

  def build_embeddings(self, force: bool = False):
    """
    Precalcula o carga desde caché los embeddings de todos los nodos.
    Si ya están en memoria y no se fuerza, no hace nada.
    """
    if not force and self._node_vectors is not None and self._node_vectors.size > 0:
      return
    if not force and self._load_cache():
      return

    model = self._load_model()
    nodes = self.taxonomy.embedding_nodes()

    self._node_ids = [n.id for n in nodes]
    self._node_texts = {n.id: self._node_text(n) for n in nodes}

    texts = [f"passage: {self._node_texts[nid]}" for nid in self._node_ids]
    logger.info(f"Generando embeddings para {len(texts)} nodos de taxonomía...")
    vectors = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    self._node_vectors = vectors

    self._save_cache()

  def encode_query(self, text: str) -> np.ndarray:
    """Codifica un término de query (CV/sílabo) con la instrucción adecuada."""
    model = self._load_model()
    formatted = f"query: {text}"
    return model.encode(formatted, convert_to_numpy=True)

  def find_nearest_nodes(
    self,
    text: str,
    top_k: int = 5,
    as_query: bool = True,
  ) -> List[Tuple[TaxonomyNode, float]]:
    """
    Retorna los top_k nodos más cercanos al texto dado.
    El texto se trata como query (CV/sílabo).
    """
    self.build_embeddings()
    if self._node_vectors is None or self._node_vectors.size == 0:
      return []

    query_vec = self.encode_query(text)

    if query_vec.ndim == 1:
      query_vec = query_vec.reshape(1, -1)

    # Normalizar para usar distancia coseno = producto punto de vectores normalizados.
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    node_norms = self._node_vectors / (np.linalg.norm(self._node_vectors, axis=1, keepdims=True) + 1e-10)

    similarities = np.dot(node_norms, query_norm.T).flatten()
    top_indices = np.argsort(similarities)[::-1][:top_k]

    results = []
    for idx in top_indices:
      node = self.taxonomy.get_node(self._node_ids[idx])
      if node:
        results.append((node, float(similarities[idx])))
    return results


# Singleton global para reutilización.
_taxonomy_embedder: Optional[TaxonomyEmbedder] = None


def get_taxonomy_embedder(taxonomy: Optional[Taxonomy] = None) -> TaxonomyEmbedder:
  global _taxonomy_embedder
  if _taxonomy_embedder is None:
    _taxonomy_embedder = TaxonomyEmbedder(taxonomy=taxonomy)
  return _taxonomy_embedder
