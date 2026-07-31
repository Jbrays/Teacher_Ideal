from __future__ import annotations
import heapq
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional, Iterator


DEFAULT_HIERARCHY_WEIGHT = 0.72

# La prioridad sólo desempata representaciones equivalentes del mismo término.
# No crea relaciones ni modifica la semántica de las fuentes.
SOURCE_PRIORITY = {
    "esco_1_2_1": 10,
    "cncf_glossary": 20,
    "cncf_landscape": 30,
    "cso_3_5": 40,
    "acm_ccs_2012": 50,
    "sfia_9": 60,
    "itil_4": 70,
    "onet_30_3": 80,
}


@dataclass
class TaxonomyNode:
    id: str
    name: str
    type: str  # "root", "branch", "leaf"
    aliases: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    children: List[TaxonomyNode] = field(default_factory=list)
    domain: Optional[str] = None
    source: Optional[str] = None
    external_id: Optional[str] = None
    description: Optional[str] = None
    kind: str = "concept"
    source_version: Optional[str] = None
    labels: Dict[str, str] = field(default_factory=dict)
    embedding_enabled: bool = True
    external_url: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    hierarchy_weight: float = DEFAULT_HIERARCHY_WEIGHT

    def all_names(self) -> List[str]:
        """Todos los nombres/aliases por los que se puede referir a este nodo."""
        return list(dict.fromkeys([self.name, *self.labels.values(), *self.aliases]))

    def path(self, taxonomy: Taxonomy) -> List[TaxonomyNode]:
        """Devuelve la rama desde la raíz hasta este nodo."""
        path = [self]
        current = self
        while current.parent_id:
            parent = taxonomy.get_node(current.parent_id)
            if not parent:
                break
            path.insert(0, parent)
            current = parent
        return path

    def is_leaf(self) -> bool:
        return self.type == "leaf"

    def is_branch(self) -> bool:
        return self.type in ("branch", "root")


@dataclass(frozen=True)
class TaxonomyRelation:
    source_id: str
    target_id: str
    relation_type: str
    weight: float
    directed: bool = False
    source: Optional[str] = None
    source_version: Optional[str] = None
    external_id: Optional[str] = None
    provenance: Dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


class Taxonomy:
    def __init__(
        self,
        roots: List[TaxonomyNode],
        relations: Optional[List[TaxonomyRelation]] = None,
        version: Optional[str] = None,
        sources: Optional[List[dict]] = None,
    ):
        self.roots = roots
        self.relations = relations or []
        self.version = version
        self.sources = sources or []
        self._node_index: Dict[str, TaxonomyNode] = {}
        self._alias_index: Dict[str, List[TaxonomyNode]] = {}
        self._graph: Dict[str, List[tuple[str, float, str]]] = {}
        self._equivalence_graph: Dict[str, set[str]] = {}
        self._similarity_cache: Dict[tuple[str, str, int], float] = {}
        self._build_indexes()

    @classmethod
    def from_file(cls, path: Optional[str] = None) -> Taxonomy:
        if path is None:
            path = os.path.join(os.path.dirname(__file__), "taxonomy.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict) -> Taxonomy:
        roots = []
        for root_data in data.get("roots", []):
            roots.append(cls._build_node(root_data, parent_id=None))
        relations = [
            TaxonomyRelation(
                source_id=relation["source_id"],
                target_id=relation["target_id"],
                relation_type=relation["relation_type"],
                weight=float(relation.get("weight", 0.0)),
                directed=bool(relation.get("directed", False)),
                source=relation.get("source"),
                source_version=relation.get("source_version"),
                external_id=relation.get("external_id"),
                provenance=relation.get("provenance") or {},
            )
            for relation in data.get("relations", [])
        ]
        sources = data.get("sources", [])
        if sources and isinstance(sources[0], str):
            sources = [{"id": source} for source in sources]
        return cls(
            roots,
            relations=relations,
            version=data.get("version"),
            sources=sources,
        )

    @classmethod
    def _build_node(cls, data: Dict, parent_id: Optional[str]) -> TaxonomyNode:
        node = TaxonomyNode(
            id=data["id"],
            name=data["name"],
            type=data.get("type", "leaf"),
            aliases=[a.strip() for a in data.get("aliases", []) if a.strip()],
            parent_id=parent_id,
            domain=data.get("domain"),
            source=data.get("source"),
            external_id=data.get("external_id"),
            description=data.get("description"),
            kind=data.get("kind", "concept"),
            source_version=data.get("source_version"),
            labels={
                language: label.strip()
                for language, label in (data.get("labels") or {}).items()
                if isinstance(label, str) and label.strip()
            },
            embedding_enabled=bool(data.get("embedding_enabled", True)),
            external_url=data.get("external_url"),
            attributes=data.get("attributes") or {},
            hierarchy_weight=float(
                data.get("hierarchy_weight", DEFAULT_HIERARCHY_WEIGHT)
            ),
        )
        for child_data in data.get("children", []):
            child = cls._build_node(child_data, parent_id=node.id)
            node.children.append(child)
        return node

    def _build_indexes(self):
        self._node_index = {}
        self._alias_index = {}
        self._graph = {}
        self._equivalence_graph = {}
        self._similarity_cache = {}
        for node in self.walk():
            self._node_index[node.id] = node
            for name in node.all_names():
                normalized = self._normalize(name)
                if normalized not in self._alias_index:
                    self._alias_index[normalized] = []
                if node not in self._alias_index[normalized]:
                    self._alias_index[normalized].append(node)

        def add_graph_edge(
            source_id: str,
            target_id: str,
            weight: float,
            relation_type: str,
        ) -> None:
            if weight <= 0 or source_id == target_id:
                return
            if source_id not in self._node_index or target_id not in self._node_index:
                return
            self._graph.setdefault(source_id, []).append(
                (target_id, min(1.0, weight), relation_type)
            )

        # Las raíces sólo organizan fuentes; no representan similitud. Así se
        # evita que dos tecnologías no relacionadas coincidan por compartir raíz.
        for node in self.walk():
            if not node.parent_id:
                continue
            parent = self.get_node(node.parent_id)
            if parent is None or parent.type == "root":
                continue
            add_graph_edge(
                node.id,
                parent.id,
                node.hierarchy_weight,
                "broader",
            )
            add_graph_edge(
                parent.id,
                node.id,
                node.hierarchy_weight,
                "narrower",
            )

        equivalent_types = {"equivalent", "exact_label_match", "same_as"}
        for relation in self.relations:
            add_graph_edge(
                relation.source_id,
                relation.target_id,
                relation.weight,
                relation.relation_type,
            )
            # Para matching, una relación semántica se puede recorrer en ambos
            # sentidos aunque su dirección original se conserve como metadato.
            add_graph_edge(
                relation.target_id,
                relation.source_id,
                relation.weight,
                relation.relation_type,
            )
            if relation.relation_type in equivalent_types:
                self._equivalence_graph.setdefault(relation.source_id, set()).add(
                    relation.target_id
                )
                self._equivalence_graph.setdefault(relation.target_id, set()).add(
                    relation.source_id
                )

    @staticmethod
    def _normalize(text: str) -> str:
        text = unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("utf-8")
        return " ".join(text.lower().split())

    @staticmethod
    def _canonical_lookup_key(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text)
        normalized = normalized.encode("ascii", "ignore").decode("ascii").casefold()
        normalized = re.sub(r"[^a-z0-9+#.]+", " ", normalized)
        return " ".join(normalized.split())

    def canonical_label_lookup(self) -> Dict[str, str]:
        """
        Etiquetas oficiales resolubles hacia el nombre canónico preferido.

        Nombres y traducciones canónicas tienen prioridad sobre aliases. Una
        etiqueta ambigua sólo se admite si todos sus nodos son equivalentes.
        """
        canonical_index: Dict[str, List[TaxonomyNode]] = {}
        alias_index: Dict[str, List[TaxonomyNode]] = {}

        def add(
            index: Dict[str, List[TaxonomyNode]],
            label: str,
            node: TaxonomyNode,
        ) -> None:
            key = self._canonical_lookup_key(label)
            if not key:
                return
            matches = index.setdefault(key, [])
            if all(existing.id != node.id for existing in matches):
                matches.append(node)

        for node in self.walk():
            if node.type == "root" or node.source == "auto":
                continue
            for label in dict.fromkeys([node.name, *node.labels.values()]):
                add(canonical_index, label, node)
            for alias in node.aliases:
                add(alias_index, alias, node)

        lookup: Dict[str, str] = {}
        for index in (canonical_index, alias_index):
            for key, candidates in index.items():
                if key in lookup:
                    continue
                preferred = self.preferred_node(candidates)
                if preferred is not None:
                    lookup[key] = preferred.name
        return lookup

    def walk(self) -> Iterator[TaxonomyNode]:
        def _walk(nodes):
            for node in nodes:
                yield node
                yield from _walk(node.children)
        yield from _walk(self.roots)

    def get_node(self, node_id: str) -> Optional[TaxonomyNode]:
        return self._node_index.get(node_id)

    def get_nodes_by_alias(self, text: str) -> List[TaxonomyNode]:
        return self._alias_index.get(self._normalize(text), [])

    def all_leaves(self) -> List[TaxonomyNode]:
        return [n for n in self.walk() if n.is_leaf()]

    def all_nodes(self) -> List[TaxonomyNode]:
        return list(self.walk())

    def embedding_nodes(self) -> List[TaxonomyNode]:
        """
        Nodos candidatos a búsqueda semántica, deduplicados por componentes de
        equivalencia para no introducir empates artificiales entre fuentes.
        """
        selected: List[TaxonomyNode] = []
        seen: set[str] = set()
        for node in sorted(
            self.all_nodes(),
            key=lambda item: (SOURCE_PRIORITY.get(item.source or "", 999), item.id),
        ):
            if (
                node.id in seen
                or node.type == "root"
                or node.source == "auto"
                or not node.embedding_enabled
            ):
                continue
            component = self.equivalent_component(node.id)
            seen.update(component)
            selected.append(node)
        return selected

    def equivalent_component(self, node_id: str) -> set[str]:
        if node_id not in self._node_index:
            return set()
        visited = {node_id}
        pending = [node_id]
        while pending:
            current = pending.pop()
            for neighbour in self._equivalence_graph.get(current, set()):
                if neighbour not in visited:
                    visited.add(neighbour)
                    pending.append(neighbour)
        return visited

    def are_equivalent(self, node_ids: List[str]) -> bool:
        ids = {node_id for node_id in node_ids if node_id in self._node_index}
        if not ids:
            return False
        first = next(iter(ids))
        return ids.issubset(self.equivalent_component(first))

    def preferred_node(
        self,
        candidates: Optional[List[TaxonomyNode]],
    ) -> Optional[TaxonomyNode]:
        if not candidates:
            return None
        unique = {node.id: node for node in candidates}
        if len(unique) == 1:
            return next(iter(unique.values()))
        if not self.are_equivalent(list(unique)):
            return None
        return min(
            unique.values(),
            key=lambda node: (SOURCE_PRIORITY.get(node.source or "", 999), node.id),
        )

    def semantic_similarity(
        self,
        source_id: str,
        target_id: str,
        max_hops: int = 4,
    ) -> float:
        """
        Máximo producto de pesos entre dos nodos del grafo semántico.

        El límite de saltos impide que cadenas largas de relaciones débiles
        conviertan conceptos remotos en cobertura efectiva.
        """
        if source_id == target_id:
            return 1.0
        if source_id not in self._node_index or target_id not in self._node_index:
            return 0.0
        if self.are_equivalent([source_id, target_id]):
            return 1.0

        cache_key = tuple(sorted((source_id, target_id))) + (max_hops,)
        cached = self._similarity_cache.get(cache_key)
        if cached is not None:
            return cached

        best: Dict[tuple[str, int], float] = {(source_id, 0): 1.0}
        queue: List[tuple[float, int, str]] = [(-1.0, 0, source_id)]
        answer = 0.0
        while queue:
            negative_score, hops, current = heapq.heappop(queue)
            score = -negative_score
            if current == target_id:
                answer = score
                break
            if hops >= max_hops:
                continue
            for neighbour, edge_weight, _relation_type in self._graph.get(current, []):
                candidate = score * edge_weight
                state = (neighbour, hops + 1)
                if candidate <= best.get(state, 0.0):
                    continue
                best[state] = candidate
                heapq.heappush(queue, (-candidate, hops + 1, neighbour))

        answer = round(answer, 3)
        self._similarity_cache[cache_key] = answer
        return answer

    def common_ancestor(self, node_a: TaxonomyNode, node_b: TaxonomyNode) -> Optional[TaxonomyNode]:
        path_a = {n.id for n in node_a.path(self)}
        for n in reversed(node_b.path(self)):
            if n.id in path_a:
                return n
        return None

    def distance_to_ancestor(self, node: TaxonomyNode, ancestor: TaxonomyNode) -> int:
        """Número de saltos desde el nodo hasta el ancestro. 0 si son el mismo."""
        if node.id == ancestor.id:
            return 0
        path = node.path(self)
        for i, n in enumerate(path):
            if n.id == ancestor.id:
                return len(path) - i - 1
        return -1
