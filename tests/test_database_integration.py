"""Prueba opt-in para una base PostgreSQL aislada.

Se ejecuta sólo cuando TEST_DATABASE_URL está definido. Nunca debe apuntar a
producción: crea el esquema faltante, sincroniza el catálogo oficial y usa un
docente efímero identificado con un UUID.
"""

import os
import unittest
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(TEST_DATABASE_URL, "TEST_DATABASE_URL no configurada")
class IsolatedDatabaseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")

        from backend.database.db_session import Base
        from backend.database import models as database_models
        from backend.database.schema_migrations import migrate_database_schema

        assert database_models
        cls.engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
        migrate_database_schema(cls.engine, Base.metadata)
        cls.Session = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def test_static_taxonomy_and_teacher_node_foreign_key(self):
        from backend.database.models import Docente, DocenteNodo, Nodo, NodoRelacion
        from backend.services.taxonomy_service import TaxonomyService

        drive_file_id = f"codex-taxonomy-test-{uuid.uuid4()}"
        db = self.Session()
        try:
            docente = Docente(
                drive_file_id=drive_file_id,
                propietario_email="integration-test@example.invalid",
                nombre="Docente de integración",
                perfil_tecnico=[
                    {
                        "es": "Inteligencia artificial",
                        "en": "Artificial intelligence",
                    },
                    {
                        "es": "Seguridad de la información",
                        "en": "Seguridad de la información",
                    },
                ],
            )
            db.add(docente)
            db.commit()
            db.refresh(docente)

            saved = TaxonomyService(db).process_docente(docente.id)
            node_count = db.query(Nodo).count()
            relation_count = db.query(NodoRelacion).count()
            associations = (
                db.query(DocenteNodo)
                .filter(DocenteNodo.docente_id == docente.id)
                .all()
            )

            self.assertGreater(node_count, 100)
            self.assertGreater(relation_count, 100)
            self.assertIsNone(db.query(Nodo).filter(Nodo.id == "emergentes").first())
            self.assertEqual(saved, 2)
            self.assertEqual(len(associations), 2)
            self.assertEqual(
                {association.nodo_id for association in associations},
                {
                    "cso.artificial_intelligence",
                    "esco.skill.8088750d_8388_4170_a76f_48354c469c44",
                },
            )
            for association in associations:
                self.assertIsNotNone(
                    db.query(Nodo)
                    .filter(Nodo.id == association.nodo_id)
                    .first()
                )
        finally:
            db.rollback()
            docente = (
                db.query(Docente)
                .filter(Docente.drive_file_id == drive_file_id)
                .first()
            )
            if docente:
                db.delete(docente)
                db.commit()
            db.close()


if __name__ == "__main__":
    unittest.main()
