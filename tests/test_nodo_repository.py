import json
import os
import tempfile
import unittest

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")

from backend.database import models as database_models
from backend.database.db_session import Base
from backend.database.models import Nodo, NodoRelacion
from backend.database.schema_migrations import migrate_database_schema
from backend.repositories.nodo_repo import NodoRepository


class NodoRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_sync_persists_source_metadata_and_typed_relations(self):
        catalog = {
            "version": "test",
            "roots": [{
                "id": "source",
                "name": "Source",
                "type": "root",
                "kind": "root",
                "source": "official_source",
                "source_version": "1.0",
                "embedding_enabled": False,
                "children": [
                    {
                        "id": "source.concept",
                        "name": "Concept",
                        "type": "leaf",
                        "kind": "concept",
                        "aliases": ["Concept alias"],
                        "labels": {"en": "Concept", "es": "Concepto"},
                        "source": "official_source",
                        "source_version": "1.0",
                        "external_id": "concept-1",
                        "external_url": "https://example.invalid/concept-1",
                        "description": "Official concept.",
                        "embedding_enabled": True,
                        "attributes": {"status": "active"},
                        "children": [],
                    },
                    {
                        "id": "source.product",
                        "name": "Product",
                        "type": "leaf",
                        "kind": "technology",
                        "source": "official_source",
                        "source_version": "1.0",
                        "embedding_enabled": False,
                        "children": [],
                    },
                ],
            }],
            "relations": [{
                "source_id": "source.product",
                "target_id": "source.concept",
                "relation_type": "official_alias_reference",
                "weight": 0.78,
                "directed": False,
                "source": "generated_crosswalk",
                "source_version": "test",
                "provenance": {"method": "test"},
            }],
        }

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            encoding="utf-8",
        ) as file:
            json.dump(catalog, file)
            file.flush()
            db = self.Session()
            try:
                repository = NodoRepository(db)
                self.assertEqual(repository.sync_from_taxonomy(file.name), 3)
                db.commit()

                concept = db.get(Nodo, "source.concept")
                relation = db.query(NodoRelacion).one()
                self.assertEqual(concept.labels["es"], "Concepto")
                self.assertEqual(concept.source_attributes["status"], "active")
                self.assertEqual(
                    relation.relation_type,
                    "official_alias_reference",
                )
                self.assertEqual(relation.provenance["method"], "test")

                self.assertEqual(repository.sync_from_taxonomy(file.name), 3)
                self.assertEqual(db.query(NodoRelacion).count(), 1)
            finally:
                db.close()

    def test_migrates_legacy_catalog_schema_without_removing_nodes(self):
        legacy_engine = create_engine("sqlite:///:memory:")
        with legacy_engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE nodos (
                    id VARCHAR PRIMARY KEY,
                    parent_id VARCHAR,
                    name VARCHAR NOT NULL,
                    node_type VARCHAR NOT NULL,
                    aliases JSON,
                    domain VARCHAR,
                    version VARCHAR,
                    created_at DATETIME
                )
            """))
            connection.execute(text("""
                INSERT INTO nodos (id, name, node_type, aliases, version)
                VALUES ('legacy.node', 'Legacy node', 'leaf', '[]', 'old')
            """))

        migrate_database_schema(legacy_engine, Base.metadata)

        columns = {
            column["name"]
            for column in inspect(legacy_engine).get_columns("nodos")
        }
        with legacy_engine.connect() as connection:
            legacy_count = connection.execute(
                text("SELECT count(*) FROM nodos WHERE id = 'legacy.node'")
            ).scalar_one()

        self.assertTrue({
            "source",
            "source_version",
            "external_id",
            "external_url",
            "description",
            "kind",
            "labels",
            "embedding_enabled",
            "source_attributes",
        }.issubset(columns))
        self.assertIn(
            "nodo_relaciones",
            inspect(legacy_engine).get_table_names(),
        )
        self.assertEqual(legacy_count, 1)
        legacy_engine.dispose()


if __name__ == "__main__":
    unittest.main()
