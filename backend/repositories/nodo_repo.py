"""Persistencia del catálogo de nodos y sus relaciones tipadas."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.database.models import Nodo, NodoRelacion

logger = logging.getLogger(__name__)


class NodoRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, nodo_id: str) -> Optional[Nodo]:
        return self.db.query(Nodo).filter(Nodo.id == nodo_id).first()

    @staticmethod
    def _node_row(node_data: dict, parent_id: Optional[str], version: str) -> dict:
        aliases = node_data.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        return {
            "id": node_data["id"],
            "parent_id": parent_id,
            "name": node_data["name"],
            "node_type": node_data.get("type", "leaf"),
            "aliases": aliases,
            "domain": node_data.get("domain"),
            "source": node_data.get("source"),
            "source_version": node_data.get("source_version"),
            "external_id": node_data.get("external_id"),
            "external_url": node_data.get("external_url"),
            "description": node_data.get("description"),
            "kind": node_data.get("kind", "concept"),
            "labels": node_data.get("labels") or {},
            "embedding_enabled": bool(node_data.get("embedding_enabled", True)),
            "source_attributes": node_data.get("attributes") or {},
            "version": version,
        }

    @staticmethod
    def _relation_row(relation: dict, version: str) -> dict:
        return {
            "source_nodo_id": relation["source_id"],
            "target_nodo_id": relation["target_id"],
            "relation_type": relation["relation_type"],
            "weight": float(relation.get("weight", 0.0)),
            "directed": bool(relation.get("directed", False)),
            "source": relation.get("source") or "unknown",
            "source_version": relation.get("source_version"),
            "external_id": relation.get("external_id"),
            "provenance": relation.get("provenance") or {},
            "version": version,
        }

    def sync_from_taxonomy(self, taxonomy_path: Optional[str] = None) -> int:
        """
        Inserta o actualiza el catálogo sin borrar referencias históricas.

        Los nodos se sincronizan por profundidad para satisfacer la FK
        padre-hijo. Las relaciones se cargan sólo después de que todos los nodos
        existen.
        """
        path = taxonomy_path or str(settings.taxonomy_path)
        with open(path, "r", encoding="utf-8") as source:
            data = json.load(source)

        taxonomy_hash = hashlib.sha256(
            json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        catalog_version = f"taxonomy-{taxonomy_hash[:16]}"

        def walk(nodes, parent_id=None, depth=0):
            for node_data in nodes:
                if (
                    node_data.get("source") == "auto"
                    or node_data.get("id") == "emergentes"
                ):
                    continue
                yield node_data, parent_id, depth
                yield from walk(
                    node_data.get("children", []),
                    parent_id=node_data["id"],
                    depth=depth + 1,
                )

        catalog = list(walk(data.get("roots", [])))
        valid_ids = {node_data["id"] for node_data, _parent, _depth in catalog}
        relations = [
            relation
            for relation in data.get("relations", [])
            if relation.get("source_id") in valid_ids
            and relation.get("target_id") in valid_ids
        ]
        expected_nodes = len(catalog)
        expected_relations = len(relations)
        current_nodes = (
            self.db.query(func.count(Nodo.id))
            .filter(Nodo.version == catalog_version)
            .scalar()
        )
        current_relations = (
            self.db.query(func.count(NodoRelacion.id))
            .filter(NodoRelacion.version == catalog_version)
            .scalar()
        )
        if (
            current_nodes == expected_nodes
            and current_relations == expected_relations
        ):
            return expected_nodes

        by_depth: dict[int, list[tuple[dict, Optional[str]]]] = {}
        for node_data, parent_id, depth in catalog:
            by_depth.setdefault(depth, []).append((node_data, parent_id))

        if self.db.get_bind().dialect.name == "postgresql":
            self._sync_postgresql(by_depth, relations, catalog_version)
        else:
            self._sync_orm(by_depth, relations, catalog_version)
        self.db.flush()
        return expected_nodes

    def _sync_postgresql(
        self,
        by_depth: dict[int, list[tuple[dict, Optional[str]]]],
        relations: list[dict],
        catalog_version: str,
    ) -> None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        for depth in sorted(by_depth):
            rows = [
                self._node_row(node_data, parent_id, catalog_version)
                for node_data, parent_id in by_depth[depth]
            ]
            for start in range(0, len(rows), 250):
                statement = pg_insert(Nodo).values(rows[start : start + 250])
                excluded = statement.excluded
                statement = statement.on_conflict_do_update(
                    index_elements=[Nodo.id],
                    set_={
                        "parent_id": excluded.parent_id,
                        "name": excluded.name,
                        "node_type": excluded.node_type,
                        "aliases": excluded.aliases,
                        "domain": excluded.domain,
                        "source": excluded.source,
                        "source_version": excluded.source_version,
                        "external_id": excluded.external_id,
                        "external_url": excluded.external_url,
                        "description": excluded.description,
                        "kind": excluded.kind,
                        "labels": excluded.labels,
                        "embedding_enabled": excluded.embedding_enabled,
                        "source_attributes": excluded.source_attributes,
                        "version": excluded.version,
                    },
                )
                self.db.execute(statement)
            self.db.flush()

        relation_rows = [
            self._relation_row(relation, catalog_version)
            for relation in relations
        ]
        for start in range(0, len(relation_rows), 500):
            statement = pg_insert(NodoRelacion).values(
                relation_rows[start : start + 500]
            )
            excluded = statement.excluded
            statement = statement.on_conflict_do_update(
                index_elements=[
                    NodoRelacion.source_nodo_id,
                    NodoRelacion.target_nodo_id,
                    NodoRelacion.relation_type,
                    NodoRelacion.source,
                ],
                set_={
                    "weight": excluded.weight,
                    "directed": excluded.directed,
                    "source_version": excluded.source_version,
                    "external_id": excluded.external_id,
                    "provenance": excluded.provenance,
                    "version": excluded.version,
                },
            )
            self.db.execute(statement)

    def _sync_orm(
        self,
        by_depth: dict[int, list[tuple[dict, Optional[str]]]],
        relations: list[dict],
        catalog_version: str,
    ) -> None:
        existing_nodes = {node.id: node for node in self.db.query(Nodo).all()}
        for depth in sorted(by_depth):
            new_nodes = []
            for node_data, parent_id in by_depth[depth]:
                row = self._node_row(node_data, parent_id, catalog_version)
                node = existing_nodes.get(row["id"])
                if node is None:
                    node = Nodo(**row)
                    existing_nodes[node.id] = node
                    new_nodes.append(node)
                else:
                    for attribute, value in row.items():
                        if attribute != "id":
                            setattr(node, attribute, value)
            if new_nodes:
                self.db.add_all(new_nodes)
            self.db.flush()

        existing_relations = {
            (
                relation.source_nodo_id,
                relation.target_nodo_id,
                relation.relation_type,
                relation.source,
            ): relation
            for relation in self.db.query(NodoRelacion).all()
        }
        new_relations = []
        for relation_data in relations:
            row = self._relation_row(relation_data, catalog_version)
            key = (
                row["source_nodo_id"],
                row["target_nodo_id"],
                row["relation_type"],
                row["source"],
            )
            relation = existing_relations.get(key)
            if relation is None:
                relation = NodoRelacion(**row)
                existing_relations[key] = relation
                new_relations.append(relation)
            else:
                for attribute, value in row.items():
                    setattr(relation, attribute, value)
        if new_relations:
            self.db.add_all(new_relations)
