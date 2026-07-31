from __future__ import annotations

import difflib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from backend.domain.technical_terms import TechnicalTermNormalizer

from .models import Taxonomy, TaxonomyNode
from backend.core.config import settings

logger = logging.getLogger(__name__)

_CURRICULAR_PREFIXES = (
    "basic concepts of ",
    "characteristics of ",
    "components of ",
    "concepts of ",
    "definition of ",
    "definitions of ",
    "fundamentals of ",
    "introduction to ",
    "overview of ",
    "applications of ",
)

_CURRICULAR_SUFFIXES = (
    " basic concepts",
    " characteristics",
    " components",
    " concepts",
    " definition",
    " fundamentals",
    " introduction",
    " overview",
    " applications",
)

@dataclass
class ResolvedMention:
    node_id: str
    node_name: str
    node_type: str
    confidence: float
    match_type: str
    raw_mention: str
    context: str = ""
    source_section: str = ""
    explicit: bool = True

@dataclass
class ResolverResult:
    resolved: List[ResolvedMention] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)

class TaxonomyResolver:
    """
    Mapea menciones textuales crudas a nodos estables de la taxonomía.
    """

    def __init__(
        self,
        taxonomy: Taxonomy,
        fuzzy_threshold: Optional[float] = None,
        embedding_threshold: Optional[float] = None,
        embedding_min_margin: Optional[float] = None,
        emergent_threshold: Optional[float] = None,
        prefer_leaf: bool = True,
        auto_create_nodes: bool = False,
    ):
        self.taxonomy = taxonomy
        self.fuzzy_threshold = fuzzy_threshold if fuzzy_threshold is not None else settings.fuzzy_threshold
        self.embedding_threshold = embedding_threshold if embedding_threshold is not None else settings.embedding_threshold
        self.embedding_min_margin = (
            embedding_min_margin
            if embedding_min_margin is not None
            else settings.embedding_min_margin
        )
        self.prefer_leaf = prefer_leaf
        # Se conservan ambos argumentos por compatibilidad de llamada, pero la
        # taxonomía de runtime es cerrada: nunca se crean nodos desde un CV/sílabo.
        if auto_create_nodes:
            logger.warning(
                "auto_create_nodes fue solicitado, pero está deshabilitado: "
                "el runtime sólo puede resolver nodos existentes."
            )
        self.auto_create_nodes = False
        self.emergent_threshold = emergent_threshold
        self._exact_name_index: Dict[str, List[TaxonomyNode]] = {}
        self._normalized_name_index: Dict[str, List[TaxonomyNode]] = {}
        self._exact_alias_index: Dict[str, List[TaxonomyNode]] = {}
        self._normalized_alias_index: Dict[str, List[TaxonomyNode]] = {}
        self._normalized_index: Dict[str, List[TaxonomyNode]] = {}
        self._fuzzy_index: Dict[str, List[TaxonomyNode]] = {}
        self._containment_index: Dict[str, List[TaxonomyNode]] = {}
        self._canonical_label_lookup: Dict[str, str] = {}
        self._build_indexes()
        self._embedder = None

    @classmethod
    def from_file(cls, path: Optional[str] = None, **kwargs) -> "TaxonomyResolver":
        return cls(Taxonomy.from_file(path), **kwargs)

    def _get_embedder(self):
        if self._embedder is None:
            from backend.services.taxonomy_embedder import get_taxonomy_embedder
            self._embedder = get_taxonomy_embedder(taxonomy=self.taxonomy)
        return self._embedder

    def _normalize(self, text: str) -> str:
        text = unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("utf-8")
        return " ".join(text.lower().split())

    def _normalize_tokens(self, text: str) -> str:
        normalized = self._normalize(text)
        normalized = re.sub(r"[^a-z0-9+#.]+", " ", normalized)
        return " ".join(normalized.split())

    def _build_indexes(self):
        self._exact_name_index = {}
        self._normalized_name_index = {}
        self._exact_alias_index = {}
        self._normalized_alias_index = {}
        self._normalized_index = {}
        self._fuzzy_index = {}
        self._containment_index = {}
        self._canonical_label_lookup = {}

        def add(
            index: Dict[str, List[TaxonomyNode]],
            key: str,
            node: TaxonomyNode,
        ) -> None:
            matches = index.setdefault(key, [])
            if all(existing.id != node.id for existing in matches):
                matches.append(node)

        for node in self.taxonomy.walk():
            if node.type == "root" or node.source == "auto":
                continue

            canonical = node.name.strip()
            if canonical:
                add(self._exact_name_index, canonical.lower(), node)
                add(self._normalized_name_index, self._normalize(canonical), node)
                add(self._normalized_index, self._normalize(canonical), node)
                if node.embedding_enabled:
                    add(self._fuzzy_index, self._normalize(canonical), node)
                    add(self._containment_index, self._normalize_tokens(canonical), node)

            for alias in node.aliases:
                clean = alias.strip()
                if not clean:
                    continue
                add(self._exact_alias_index, clean.lower(), node)
                add(self._normalized_alias_index, self._normalize(clean), node)
                add(self._normalized_index, self._normalize(clean), node)
                if node.embedding_enabled:
                    add(self._fuzzy_index, self._normalize(clean), node)
                    add(self._containment_index, self._normalize_tokens(clean), node)

        # Extracción y resolución consumen exactamente el mismo catálogo de
        # etiquetas; los nombres canónicos tienen prioridad sobre aliases.
        self._canonical_label_lookup = self.taxonomy.canonical_label_lookup()

    def _unique_node(
        self,
        candidates: Optional[List[TaxonomyNode]],
    ) -> Optional[TaxonomyNode]:
        return self.taxonomy.preferred_node(candidates)

    def _fuzzy_match(self, text: str) -> Optional[Tuple[TaxonomyNode, float]]:
        normalized = self._normalize(text)
        if not normalized:
            return None
        candidates = [
            key
            for key, nodes in self._fuzzy_index.items()
            if self._unique_node(nodes) is not None
        ]
        if not candidates:
            return None
        matches = difflib.get_close_matches(
            normalized, candidates, n=1, cutoff=self.fuzzy_threshold
        )
        if not matches:
            return None
        best_key = matches[0]
        ratio = difflib.SequenceMatcher(None, normalized, best_key).ratio()
        node = self._unique_node(self._fuzzy_index.get(best_key))
        if node is None:
            return None
        return node, ratio

    def _strip_curricular_wrapper(self, text: str) -> Optional[str]:
        normalized = self._normalize_tokens(text)
        stripped = normalized
        for prefix in _CURRICULAR_PREFIXES:
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix):].strip()
                break
        for suffix in _CURRICULAR_SUFFIXES:
            if stripped.endswith(suffix):
                stripped = stripped[:-len(suffix)].strip()
                break
        if stripped and stripped != normalized:
            return stripped
        return None

    def _containment_match(self, text: str) -> Optional[TaxonomyNode]:
        """
        Resuelve conceptos compuestos que contienen de forma literal un nombre
        taxonómico inequívoco. Se excluyen aliases de una sola palabra para no
        convertir coincidencias parciales genéricas en evidencia técnica.
        """
        normalized = self._normalize_tokens(text)
        if not normalized:
            return None

        matches: List[Tuple[int, str, TaxonomyNode]] = []
        padded = f" {normalized} "
        mention_token_count = len(normalized.split())
        for key, candidates in self._containment_index.items():
            key_token_count = len(key.split())
            if key_token_count < 2 or len(key) < 8:
                continue
            if key_token_count / mention_token_count < 0.5:
                continue
            node = self._unique_node(candidates)
            if node is None or key == normalized:
                continue
            if f" {key} " in padded:
                matches.append((len(key), key, node))

        if not matches:
            return None

        matches.sort(key=lambda item: item[0], reverse=True)
        longest = matches[0][0]
        best_nodes = {
            item[2].id: item[2]
            for item in matches
            if item[0] == longest
        }
        if len(best_nodes) != 1:
            return None
        return next(iter(best_nodes.values()))

    def _embedding_match(self, text: str) -> Optional[Tuple[TaxonomyNode, float]]:
        try:
            embedder = self._get_embedder()
            nearest = [
                (node, score)
                for node, score in embedder.find_nearest_nodes(text, top_k=5, as_query=True)
                if node.type != "root" and node.source != "auto"
            ]
            if not nearest:
                return None
            node, score = nearest[0]
            if score < self.embedding_threshold:
                return None
            if len(nearest) > 1:
                margin = score - nearest[1][1]
                if margin < self.embedding_min_margin:
                    logger.info(
                        "Match de embedding ambiguo para '%s': score=%.4f, margen=%.4f",
                        text,
                        score,
                        margin,
                    )
                    return None
            return node, score
        except Exception as e:
            logger.warning(f"Embedding match falló para '{text}': {e}")
        return None

    def _try_match_lexical(
        self,
        text: str,
        allow_fuzzy: bool = True,
    ) -> Tuple[Optional[TaxonomyNode], float, str]:
        lower = text.lower()
        normalized = self._normalize(text)

        node = self._unique_node(self._exact_name_index.get(lower))
        if node is not None:
            return node, 1.0, "exact_name"

        node = self._unique_node(self._exact_alias_index.get(lower))
        if node is not None:
            return node, 1.0, "exact_alias"

        node = self._unique_node(self._normalized_name_index.get(normalized))
        if node is not None:
            return node, settings.normalized_match_score, "normalized_name"

        node = self._unique_node(self._normalized_alias_index.get(normalized))
        if node is not None:
            return node, settings.normalized_match_score, "normalized_alias"

        contained = self._containment_match(text)
        if contained is not None:
            return contained, settings.normalized_match_score, "contained_concept"

        if allow_fuzzy:
            fuzzy = self._fuzzy_match(text)
            if fuzzy:
                return fuzzy[0], fuzzy[1], "fuzzy"

        return None, 0.0, "none"

    def _refine_to_leaf(self, raw: str, branch: TaxonomyNode) -> Optional[TaxonomyNode]:
        raw_lower = raw.lower()
        for leaf in self.taxonomy.all_leaves():
            if not any(branch.id == anc.id for anc in leaf.path(self.taxonomy)):
                continue
            for alias in leaf.all_names():
                if alias.lower() in raw_lower:
                    return leaf
        return None

    def resolve(
        self,
        mention: str,
        context: str = "",
        source_section: str = "",
        explicit: bool = True,
        raw_mention: Optional[str] = None,
    ) -> Optional[ResolvedMention]:
        raw = (raw_mention or mention).strip()
        mention = mention.strip()
        if not mention:
            return None

        clean = mention
        node: Optional[TaxonomyNode] = None
        confidence = 0.0
        match_type = "none"

        canonicalized = self._strip_curricular_wrapper(clean)
        candidates = [canonicalized, clean] if canonicalized else [clean]
        for candidate in candidates:
            node, confidence, match_type = self._try_match_lexical(
                candidate,
                allow_fuzzy=candidate == clean,
            )
            if node is not None:
                if candidate != clean:
                    match_type = f"{match_type}+curricular_wrapper"
                break

        if node is None:
            emb = self._embedding_match(clean)
            if emb:
                node, confidence = emb[0], emb[1]
                match_type = "embedding"

        if node is None:
            return None

        if self.prefer_leaf and node.is_branch():
            refined = self._refine_to_leaf(raw, node)
            if refined and refined is not node:
                node = refined
                confidence = max(0.7, confidence - 0.1)
                match_type = f"{match_type}+leaf"

        return ResolvedMention(
            node_id=node.id,
            node_name=node.name,
            node_type=node.type,
            confidence=confidence,
            match_type=match_type,
            raw_mention=raw,
            context=context,
            source_section=source_section,
            explicit=explicit,
        )

    def resolve_many(
        self,
        mentions: List[dict],
    ) -> ResolverResult:
        resolved: List[ResolvedMention] = []
        normalized = TechnicalTermNormalizer.normalize_many(
            mentions,
            canonical_lookup=self._canonical_label_lookup,
        )
        unresolved = [item.term for item in normalized.rejected if item.term]

        for item in normalized.accepted:
            mention_to_resolve = item.en

            res = self.resolve(
                mention=mention_to_resolve,
                context=item.context,
                source_section=item.source_section,
                explicit=item.explicit,
                raw_mention=item.raw_es,
            )
            if res:
                resolved.append(res)
            else:
                unresolved.append(item.es)

        return ResolverResult(resolved=resolved, unresolved=unresolved)
