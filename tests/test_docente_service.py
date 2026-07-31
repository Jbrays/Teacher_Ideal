import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")

from backend.services.docente_service import DocenteService


class DocenteInferenceValidationTests(unittest.TestCase):
    def make_service(self) -> DocenteService:
        service = object.__new__(DocenteService)
        service._load_historial_for = Mock(return_value=[])
        return service

    def test_without_history_preserves_explicit_domains_only(self):
        service = self.make_service()
        mentions = [
            {"termino": "Gestión de proyectos", "explicito": True},
            {"termino": "Arquitectura de software", "explicito": False},
        ]

        result = service._validate_inferences(mentions, "Docente de prueba")

        self.assertEqual(result, [mentions[0]])

    def test_all_explicit_domains_do_not_require_history(self):
        service = self.make_service()
        mentions = [
            {"termino": "Gestión de procesos", "explicito": True},
            {"termino": "Tecnologías de la información", "explicito": True},
        ]

        result = service._validate_inferences(mentions, "Docente de prueba")

        self.assertEqual(result, mentions)
        service._load_historial_for.assert_not_called()

    def test_profile_builder_uses_source_catalog_lookup(self):
        service = self.make_service()
        service.canonical_lookup = {"zoom": "Zoom"}

        result = service._construir_perfil_tecnico([
            {
                "termino": "ZOOM",
                "termino_en": "Plataforma de videoconferencias",
            }
        ])

        self.assertEqual(result, [{"es": "Zoom", "en": "Zoom"}])


if __name__ == "__main__":
    unittest.main()
