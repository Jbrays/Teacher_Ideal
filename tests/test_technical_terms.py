import unittest

from backend.domain.technical_terms import TechnicalTermNormalizer
from backend.llm.prompts.cv import prompt_cv_unificado
from backend.llm.prompts.syllabus import prompt_directo_silabo
from backend.taxonomy.catalog import get_canonical_label_lookup


class TechnicalTermNormalizerTests(unittest.TestCase):
    CATALOG_LOOKUP = {
        "python": "Python",
        "zoom": "Zoom",
        "canvas": "Canvas LMS",
        "canvas lms": "Canvas LMS",
        "lms canvas": "Canvas LMS",
        "canva": "Canva",
        "modelado de procesos de negocio": "Business process modeling",
        "business process model and notation": "Business process modeling",
        "business process modeling": "Business process modeling",
        "togaf": "TOGAF",
        "togaf 10": "TOGAF",
        "togaf adm fase a": "TOGAF",
        "togaf adm phase a": "TOGAF",
        "togaf adm gestion de requisitos": "TOGAF",
        "togaf adm requirements management": "TOGAF",
    }

    def normalize(self, items):
        return TechnicalTermNormalizer.normalize_many(
            items,
            canonical_lookup=self.CATALOG_LOOKUP,
        )

    def test_replaces_descriptions_for_known_proper_names(self):
        result = self.normalize([
            {"termino": "Python", "termino_en": "Lenguaje de programación"},
            {"termino": "ZOOM", "termino_en": "Plataforma de videoconferencias"},
        ])

        self.assertEqual(
            result.profile,
            [
                {"es": "Python", "en": "Python"},
                {"es": "Zoom", "en": "Zoom"},
            ],
        )
        self.assertEqual(result.rejected, [])

    def test_accepts_real_concept_translation(self):
        result = TechnicalTermNormalizer.normalize_many([
            {
                "termino": "Inteligencia artificial",
                "termino_en": "Artificial intelligence",
            },
            {
                "termino": "Desarrollo de aplicaciones Android",
                "termino_en": "Android application development",
            },
        ])

        self.assertEqual(len(result.accepted), 2)
        self.assertEqual(result.rejected, [])

    def test_rejects_spanish_concept_in_english_field(self):
        result = TechnicalTermNormalizer.normalize_many([
            {
                "termino": "Seguridad de la información",
                "termino_en": "Seguridad de la información",
            }
        ])

        self.assertEqual(result.profile, [])
        self.assertEqual(result.rejected[0].reason, "termino_en_no_esta_en_ingles")

    def test_canvas_and_canva_are_not_merged(self):
        result = self.normalize([
            {"termino": "CANVAS", "termino_en": "Canvas LMS"},
            {"termino": "Canva", "termino_en": "Canva"},
        ])

        self.assertEqual(
            result.profile,
            [
                {"es": "Canvas LMS", "en": "Canvas LMS"},
                {"es": "Canva", "en": "Canva"},
            ],
        )

    def test_deduplicates_by_canonical_english_query(self):
        result = self.normalize([
            {"termino": "Canvas", "termino_en": "Canvas"},
            {"termino": "CANVAS LMS", "termino_en": "Canvas LMS"},
            {"termino": "LMS Canvas", "termino_en": "Canvas LMS"},
        ])

        self.assertEqual(result.profile, [{"es": "Canvas LMS", "en": "Canvas LMS"}])

    def test_rejects_conflicting_known_aliases(self):
        result = self.normalize([
            {"termino": "Canva", "termino_en": "Canvas LMS"}
        ])

        self.assertEqual(result.profile, [])
        self.assertEqual(result.rejected[0].reason, "aliases_bilingues_en_conflicto")

    def test_corrects_known_concept_mistranslation(self):
        result = self.normalize([
            {
                "termino": "Modelado de procesos de negocio",
                "termino_en": "Business Process Model and Notation",
            }
        ])

        self.assertEqual(
            result.profile,
            [{
                "es": "Modelado de procesos de negocio",
                "en": "Business process modeling",
            }],
        )

    def test_collapses_standard_versions_and_phases(self):
        result = self.normalize([
            {"termino": "TOGAF 10", "termino_en": "TOGAF 10"},
            {"termino": "TOGAF ADM Fase A", "termino_en": "TOGAF ADM Phase A"},
            {
                "termino": "TOGAF ADM Gestión de requisitos",
                "termino_en": "TOGAF ADM Requirements management",
            },
        ])

        self.assertEqual(result.profile, [{"es": "TOGAF", "en": "TOGAF"}])

    def test_real_catalog_normalizes_profile_before_persistence(self):
        result = TechnicalTermNormalizer.normalize_many(
            [
                {
                    "termino": "ZOOM",
                    "termino_en": "Plataforma de videoconferencias",
                },
                {
                    "termino": "Seguridad de la información",
                    "termino_en": "Seguridad de la información",
                },
                {
                    "termino": "Infraestructura como Código",
                    "termino_en": "Infrastructure as Code",
                },
            ],
            canonical_lookup=get_canonical_label_lookup(),
        )

        self.assertEqual(
            result.profile,
            [
                {"es": "Zoom", "en": "Zoom"},
                {
                    "es": "Seguridad de la información",
                    "en": "cyber security",
                },
                {
                    "es": "Infraestructura como Código",
                    "en": "Infrastructure as Code (IaC)",
                },
            ],
        )
        self.assertEqual(result.rejected, [])


class PromptContractTests(unittest.TestCase):
    def test_cv_prompt_forbids_definitions_in_english_field(self):
        prompt = prompt_cv_unificado("CV de prueba")

        self.assertIn("equivalente técnico exacto", prompt)
        self.assertIn("Está prohibido colocar en \"termino_en\" una definición", prompt)
        self.assertIn('"Python"/"Lenguaje de programación"', prompt)

    def test_syllabus_prompt_requires_aligned_translation_lists(self):
        prompt = prompt_directo_silabo("Sílabo de prueba")

        self.assertIn("mismo orden y la misma cantidad", prompt)
        self.assertIn('"teoria" y "teoria_en" deben tener exactamente la misma longitud', prompt)

    def test_syllabus_prompt_requires_atomic_canonical_concepts(self):
        prompt = prompt_directo_silabo("Sílabo de prueba")

        self.assertIn("UN solo concepto técnico reutilizable", prompt)
        self.assertIn("Elimina envolturas pedagógicas", prompt)
        self.assertIn("Divide enumeraciones", prompt)
        self.assertIn('las fases A-H de TOGAF se representan como "TOGAF"', prompt)


if __name__ == "__main__":
    unittest.main()
