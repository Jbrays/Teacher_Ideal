"""Importador reproducible de la colección de habilidades digitales ESCO 1.2.1."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable


SOURCE_ID = "esco_1_2_1"
SOURCE_VERSION = "1.2.1"


def _rows(archive: zipfile.ZipFile, filename: str) -> list[dict]:
    with archive.open(filename) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
        return list(csv.DictReader(text))


def _split_labels(value: str) -> list[str]:
    return list(
        dict.fromkeys(
            part.strip()
            for part in re.split(r"\s*\|\s*|\r?\n", value or "")
            if part.strip()
        )
    )


def _uri_id(uri: str, is_group: bool = False) -> str:
    fragment = uri.rstrip("/").rsplit("/", 1)[-1]
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", fragment).strip("_").lower()
    prefix = "group" if is_group else "skill"
    return f"esco.{prefix}.{safe}"


def _catalog(
    skills_rows: Iterable[dict],
    groups_rows: Iterable[dict],
) -> dict[str, dict]:
    catalog: dict[str, dict] = {}
    for row in groups_rows:
        uri = row.get("conceptUri", "").strip()
        if uri:
            catalog[uri] = {**row, "_is_group": True}
    for row in skills_rows:
        uri = row.get("conceptUri", "").strip()
        if uri:
            catalog[uri] = {**row, "_is_group": False}
    return catalog


def import_esco_digital_taxonomy(
    english_zip: str | Path,
    spanish_zip: str | Path,
) -> tuple[dict, list[dict]]:
    """
    Importa la colección digital oficial y todos sus ancestros de jerarquía.

    ESCO ofrece más de una relación ``broader`` para algunos conceptos porque
    también los vincula con ISCED. Para el árbol se prioriza el padre ESCO de
    habilidad/conocimiento; las relaciones adicionales se conservan como aristas.
    """
    with zipfile.ZipFile(english_zip) as en_archive, zipfile.ZipFile(
        spanish_zip
    ) as es_archive:
        en_catalog = _catalog(
            _rows(en_archive, "skills_en.csv"),
            _rows(en_archive, "skillGroups_en.csv"),
        )
        es_catalog = _catalog(
            _rows(es_archive, "skills_es.csv"),
            _rows(es_archive, "skillGroups_es.csv"),
        )
        digital_rows = _rows(en_archive, "digitalSkillsCollection_en.csv")
        broader_rows = _rows(en_archive, "broaderRelationsSkillPillar_en.csv")
        skill_relations = _rows(en_archive, "skillSkillRelations_en.csv")

    candidates: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in broader_rows:
        child_uri = row.get("conceptUri", "").strip()
        parent_uri = row.get("broaderUri", "").strip()
        parent_type = row.get("broaderType", "").strip()
        if child_uri and parent_uri and child_uri != parent_uri:
            candidates[child_uri].append((parent_uri, parent_type))

    def choose_parent(uri: str) -> str | None:
        options = candidates.get(uri, [])
        known = [option for option in options if option[0] in en_catalog]
        if not known:
            return None
        concept_parent = next(
            (
                parent_uri
                for parent_uri, parent_type in known
                if parent_type == "KnowledgeSkillCompetence"
            ),
            None,
        )
        return concept_parent or sorted(parent_uri for parent_uri, _ in known)[0]

    selected = {
        row.get("conceptUri", "").strip()
        for row in digital_rows
        if row.get("conceptUri", "").strip() in en_catalog
    }
    pending = list(selected)
    parent_by_uri: dict[str, str] = {}
    while pending:
        uri = pending.pop()
        parent_uri = choose_parent(uri)
        if parent_uri is None:
            continue
        parent_by_uri[uri] = parent_uri
        if parent_uri not in selected:
            selected.add(parent_uri)
            pending.append(parent_uri)

    children_by_uri: dict[str, list[str]] = defaultdict(list)
    for child_uri, parent_uri in parent_by_uri.items():
        if child_uri in selected and parent_uri in selected:
            children_by_uri[parent_uri].append(child_uri)

    def build_node(uri: str, lineage: set[str] | None = None) -> dict:
        lineage = set(lineage or ())
        if uri in lineage:
            raise ValueError(f"Ciclo detectado en jerarquía ESCO: {uri}")
        lineage.add(uri)

        en = en_catalog[uri]
        es = es_catalog.get(uri, {})
        name = (en.get("preferredLabel") or uri.rsplit("/", 1)[-1]).strip()
        spanish_name = (es.get("preferredLabel") or "").strip()
        aliases = [
            *_split_labels(en.get("altLabels", "")),
            *_split_labels(en.get("hiddenLabels", "")),
            spanish_name,
            *_split_labels(es.get("altLabels", "")),
            *_split_labels(es.get("hiddenLabels", "")),
        ]
        aliases = [
            alias
            for alias in dict.fromkeys(aliases)
            if alias and alias.casefold() != name.casefold()
        ]
        child_uris = sorted(
            children_by_uri.get(uri, []),
            key=lambda child: en_catalog[child].get("preferredLabel", "").casefold(),
        )
        children = [build_node(child, lineage) for child in child_uris]
        is_group = bool(en.get("_is_group"))
        description = (
            en.get("description")
            or en.get("definition")
            or en.get("scopeNote")
            or ""
        ).strip()
        return {
            "id": _uri_id(uri, is_group=is_group),
            "name": name,
            "type": "branch" if children else "leaf",
            "kind": "group" if is_group else "skill",
            "aliases": aliases,
            "labels": {
                language: label
                for language, label in {"en": name, "es": spanish_name}.items()
                if label
            },
            "source": SOURCE_ID,
            "source_version": SOURCE_VERSION,
            "external_id": uri,
            "external_url": uri,
            "description": description or None,
            "embedding_enabled": not is_group,
            "attributes": {
                "skill_type": en.get("skillType") or None,
                "reuse_level": en.get("reuseLevel") or None,
                "status": en.get("status") or None,
                "digital_collection": uri
                in {
                    row.get("conceptUri", "").strip()
                    for row in digital_rows
                },
            },
            "children": children,
        }

    root_uris = sorted(
        (uri for uri in selected if uri not in parent_by_uri),
        key=lambda uri: en_catalog[uri].get("preferredLabel", "").casefold(),
    )
    root = {
        "id": SOURCE_ID,
        "name": "ESCO 1.2.1 Digital Skills and Knowledge",
        "type": "root",
        "kind": "root",
        "aliases": ["ESCO Digital", "ESCO digital skills"],
        "source": SOURCE_ID,
        "source_version": SOURCE_VERSION,
        "external_id": "digitalSkillsCollection",
        "external_url": "https://esco.ec.europa.eu/en/classification/skill",
        "description": (
            "Official ESCO digital skills and knowledge collection with its "
            "complete ESCO ancestor hierarchy."
        ),
        "embedding_enabled": False,
        "children": [build_node(uri) for uri in root_uris],
    }

    relations: list[dict] = []
    seen_relations: set[tuple[str, str, str]] = set()

    def add_relation(
        source_uri: str,
        target_uri: str,
        relation_type: str,
        weight: float,
        external_id: str,
    ) -> None:
        if source_uri not in selected or target_uri not in selected:
            return
        source_id = _uri_id(
            source_uri, is_group=bool(en_catalog[source_uri].get("_is_group"))
        )
        target_id = _uri_id(
            target_uri, is_group=bool(en_catalog[target_uri].get("_is_group"))
        )
        key = (source_id, target_id, relation_type)
        if source_id == target_id or key in seen_relations:
            return
        seen_relations.add(key)
        relations.append(
            {
                "source_id": source_id,
                "target_id": target_id,
                "relation_type": relation_type,
                "weight": weight,
                "directed": True,
                "source": SOURCE_ID,
                "source_version": SOURCE_VERSION,
                "external_id": external_id,
                "provenance": {"source_uri": source_uri, "target_uri": target_uri},
            }
        )

    for child_uri, options in candidates.items():
        selected_parent = parent_by_uri.get(child_uri)
        for parent_uri, _parent_type in options:
            if parent_uri != selected_parent:
                add_relation(
                    child_uri,
                    parent_uri,
                    "broader",
                    0.72,
                    "broaderRelationsSkillPillar",
                )

    # Estas relaciones se conservan para trazabilidad, pero no generan
    # similitud: required/optional no significa equivalencia de competencias.
    for row in skill_relations:
        add_relation(
            row.get("originalSkillUri", "").strip(),
            row.get("relatedSkillUri", "").strip(),
            f"esco_{row.get('relationType', 'related').strip().lower()}",
            0.0,
            "skillSkillRelations",
        )

    return root, relations
