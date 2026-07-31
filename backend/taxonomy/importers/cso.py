"""Importador de Computer Science Ontology 3.5."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections import defaultdict, deque
from pathlib import Path


SOURCE_ID = "cso_3_5"
SOURCE_VERSION = "3.5"
TOPIC_PREFIX = "https://cso.kmi.open.ac.uk/topics/"


def _resource(value: str) -> str:
    value = value.strip()
    if value.startswith("<") and value.endswith(">"):
        return value[1:-1]
    return value


def _topic_slug(uri: str) -> str:
    return uri.rstrip("/").rsplit("/", 1)[-1]


def _node_id(uri: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", _topic_slug(uri)).strip("_").lower()
    return f"cso.{slug}"


def _literal(value: str) -> str:
    value = value.strip()
    # El CSV 3.5 no escapa las comillas internas del literal RDF; csv.reader
    # las consume y entrega, por ejemplo, ``artificial intelligence@en .``.
    match = re.match(r'^"?(.*?)"?@[a-zA-Z-]+\s*\.\s*$', value)
    return match.group(1).strip('"') if match else value.strip('"')


def import_cso_taxonomy(csv_zip: str | Path) -> tuple[dict, list[dict]]:
    with zipfile.ZipFile(csv_zip) as archive:
        filename = next(name for name in archive.namelist() if name.endswith(".csv"))
        with archive.open(filename) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
            triples = [tuple(row[:3]) for row in reader if len(row) >= 3]

    labels: dict[str, str] = {}
    preferred: dict[str, str] = {}
    super_edges: list[tuple[str, str]] = []
    contributes: list[tuple[str, str]] = []
    equivalents: list[tuple[str, str]] = []
    topics: set[str] = set()

    for raw_subject, raw_predicate, raw_object in triples:
        subject = _resource(raw_subject)
        predicate = _resource(raw_predicate).rsplit("#", 1)[-1].rsplit("/", 1)[-1]
        if subject.startswith(TOPIC_PREFIX):
            topics.add(subject)
        if predicate == "label":
            labels[subject] = _literal(raw_object)
            continue
        target = _resource(raw_object)
        if target.startswith(TOPIC_PREFIX):
            topics.add(target)
        if predicate == "preferentialEquivalent":
            preferred[subject] = target
        elif predicate == "superTopicOf":
            super_edges.append((subject, target))
        elif predicate == "contributesTo":
            contributes.append((subject, target))
        elif predicate == "relatedEquivalent":
            equivalents.append((subject, target))

    def canonical(uri: str) -> str:
        visited: set[str] = set()
        current = uri
        while current in preferred and preferred[current] not in visited:
            visited.add(current)
            next_uri = preferred[current]
            if next_uri == current:
                break
            current = next_uri
        return current

    aliases_by_uri: dict[str, set[str]] = defaultdict(set)
    for topic in topics:
        canonical_uri = canonical(topic)
        label = labels.get(topic) or _topic_slug(topic).replace("_", " ").replace("-", " ")
        aliases_by_uri[canonical_uri].add(label)

    canonical_super = {
        (canonical(parent), canonical(child))
        for parent, child in super_edges
        if canonical(parent) != canonical(child)
    }
    children_by_uri: dict[str, set[str]] = defaultdict(set)
    parents_by_uri: dict[str, set[str]] = defaultdict(set)
    for parent, child in canonical_super:
        children_by_uri[parent].add(child)
        parents_by_uri[child].add(parent)

    computer_science = canonical(f"{TOPIC_PREFIX}computer_science")
    reachable = {computer_science}
    depth = {computer_science: 0}
    queue = deque([computer_science])
    while queue:
        parent = queue.popleft()
        for child in sorted(children_by_uri.get(parent, set())):
            if child not in reachable:
                reachable.add(child)
                depth[child] = depth[parent] + 1
                queue.append(child)

    parent_by_uri: dict[str, str] = {}
    for child in reachable - {computer_science}:
        candidates = [
            parent
            for parent in parents_by_uri.get(child, set())
            if parent in reachable and depth.get(parent, -1) < depth.get(child, 10**6)
        ]
        if candidates:
            parent_by_uri[child] = max(
                candidates,
                key=lambda parent: (depth.get(parent, -1), _topic_slug(parent)),
            )

    tree_children: dict[str, list[str]] = defaultdict(list)
    for child, parent in parent_by_uri.items():
        tree_children[parent].append(child)

    def display_name(uri: str) -> str:
        raw = labels.get(uri) or _topic_slug(uri).replace("_", " ").replace("-", " ")
        return raw[:1].upper() + raw[1:]

    def build_node(uri: str, lineage: set[str] | None = None) -> dict:
        lineage = set(lineage or ())
        if uri in lineage:
            raise ValueError(f"Ciclo detectado en CSO: {uri}")
        lineage.add(uri)
        children = [
            build_node(child, lineage)
            for child in sorted(
                tree_children.get(uri, []), key=lambda item: display_name(item).casefold()
            )
        ]
        name = display_name(uri)
        aliases = sorted(
            {
                alias
                for alias in aliases_by_uri.get(uri, set())
                if alias and alias.casefold() != name.casefold()
            },
            key=str.casefold,
        )
        return {
            "id": _node_id(uri),
            "name": name,
            "type": "branch" if children else "leaf",
            "kind": "concept",
            "aliases": aliases,
            "labels": {"en": name},
            "source": SOURCE_ID,
            "source_version": SOURCE_VERSION,
            "external_id": uri,
            "external_url": uri,
            "description": None,
            "embedding_enabled": True,
            "children": children,
        }

    root = {
        "id": SOURCE_ID,
        "name": "Computer Science Ontology 3.5",
        "type": "root",
        "kind": "root",
        "aliases": ["CSO", "Computer Science Ontology"],
        "source": SOURCE_ID,
        "source_version": SOURCE_VERSION,
        "external_id": "CSO.3.5",
        "external_url": "https://cso.kmi.open.ac.uk/downloads",
        "description": "Ontology of computer-science research topics.",
        "embedding_enabled": False,
        "children": [build_node(computer_science)],
    }

    relations: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def add_relation(
        source_uri: str,
        target_uri: str,
        relation_type: str,
        weight: float,
    ) -> None:
        source_uri = canonical(source_uri)
        target_uri = canonical(target_uri)
        if (
            source_uri == target_uri
            or source_uri not in reachable
            or target_uri not in reachable
        ):
            return
        key = (_node_id(source_uri), _node_id(target_uri), relation_type)
        if key in seen:
            return
        seen.add(key)
        relations.append(
            {
                "source_id": key[0],
                "target_id": key[1],
                "relation_type": relation_type,
                "weight": weight,
                "directed": relation_type not in {"equivalent"},
                "source": SOURCE_ID,
                "source_version": SOURCE_VERSION,
                "external_id": relation_type,
                "provenance": {
                    "source_uri": source_uri,
                    "target_uri": target_uri,
                },
            }
        )

    for parent, child in canonical_super:
        if parent_by_uri.get(child) != parent:
            add_relation(child, parent, "broader", 0.72)
    for source_uri, target_uri in equivalents:
        add_relation(source_uri, target_uri, "equivalent", 0.96)
    for source_uri, target_uri in contributes:
        # CSO indica contribución, no equivalencia. Se conserva por debajo del
        # umbral de cobertura para no afirmar dominio sustituto.
        add_relation(source_uri, target_uri, "contributes_to", 0.50)

    return root, relations
