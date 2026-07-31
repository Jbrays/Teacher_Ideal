import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")

from backend.taxonomy.models import Taxonomy
from backend.taxonomy.resolver import TaxonomyResolver


def build_taxonomy() -> Taxonomy:
    return Taxonomy.from_dict({
        "roots": [
            {
                "id": "standard",
                "name": "Standard taxonomy",
                "type": "root",
                "source": "test",
                "children": [
                    {
                        "id": "standard.ai",
                        "name": "Artificial intelligence",
                        "type": "leaf",
                        "aliases": ["AI"],
                        "source": "test",
                    },
                    {
                        "id": "standard.programming",
                        "name": "Programming languages",
                        "type": "leaf",
                        "source": "test",
                    },
                    {
                        "id": "standard.databases",
                        "name": "Database management",
                        "type": "leaf",
                        "source": "test",
                    },
                    {
                        "id": "standard.enterprise_architecture",
                        "name": "Enterprise architectures",
                        "type": "leaf",
                        "aliases": ["Enterprise architecture"],
                        "source": "test",
                    },
                    {
                        "id": "standard.electrical_circuits",
                        "name": "Electrical circuits",
                        "type": "leaf",
                        "source": "test",
                    },
                ],
            },
            {
                "id": "emergentes",
                "name": "Términos emergentes",
                "type": "root",
                "source": "auto",
                "children": [],
            },
        ]
    })


class FakeEmbedder:
    def __init__(self, results):
        self.results = results
        self.queries = []

    def find_nearest_nodes(self, text, top_k=5, as_query=True):
        self.queries.append(text)
        return self.results[:top_k]


class TaxonomyResolverTests(unittest.TestCase):
    def make_resolver(self, taxonomy=None, **kwargs):
        return TaxonomyResolver(
            taxonomy or build_taxonomy(),
            fuzzy_threshold=0.95,
            embedding_threshold=0.65,
            embedding_min_margin=0.03,
            **kwargs,
        )

    def test_uses_english_term_for_existing_taxonomy(self):
        resolver = self.make_resolver()

        result = resolver.resolve_many([
            {
                "termino": "Inteligencia artificial",
                "termino_en": "Artificial intelligence",
            }
        ])

        self.assertEqual([item.node_id for item in result.resolved], ["standard.ai"])
        self.assertEqual(result.unresolved, [])

    def test_bad_description_is_corrected_before_resolution(self):
        taxonomy = build_taxonomy()
        taxonomy.roots[0].children.append(
            type(taxonomy.roots[0].children[0])(
                id="standard.python",
                name="Python",
                type="leaf",
                source="test",
                parent_id="standard",
            )
        )
        taxonomy._build_indexes()
        resolver = self.make_resolver(taxonomy)

        result = resolver.resolve_many([
            {"termino": "Python", "termino_en": "Lenguaje de programación"}
        ])

        self.assertEqual([item.node_id for item in result.resolved], ["standard.python"])

    def test_unknown_term_does_not_create_emergent_node(self):
        taxonomy = build_taxonomy()
        initial_ids = {node.id for node in taxonomy.all_nodes()}
        resolver = self.make_resolver(taxonomy, auto_create_nodes=True)
        resolver._embedder = FakeEmbedder([])

        result = resolver.resolve_many([
            {"termino": "Unmapped Product", "termino_en": "Unmapped Product"}
        ])

        self.assertEqual(result.resolved, [])
        self.assertEqual(result.unresolved, ["Unmapped Product"])
        self.assertEqual({node.id for node in taxonomy.all_nodes()}, initial_ids)
        self.assertFalse(resolver.auto_create_nodes)

    def test_rejects_ambiguous_embedding_match(self):
        taxonomy = build_taxonomy()
        resolver = self.make_resolver(taxonomy)
        resolver._embedder = FakeEmbedder([
            (taxonomy.get_node("standard.ai"), 0.80),
            (taxonomy.get_node("standard.programming"), 0.79),
        ])

        result = resolver.resolve_many([
            {"termino": "Neural tooling", "termino_en": "Neural tooling"}
        ])

        self.assertEqual(result.resolved, [])
        self.assertEqual(result.unresolved, ["Neural tooling"])

    def test_accepts_embedding_match_with_sufficient_margin(self):
        taxonomy = build_taxonomy()
        resolver = self.make_resolver(taxonomy)
        resolver._embedder = FakeEmbedder([
            (taxonomy.get_node("standard.ai"), 0.82),
            (taxonomy.get_node("standard.programming"), 0.70),
        ])

        result = resolver.resolve_many([
            {"termino": "Neural tooling", "termino_en": "Neural tooling"}
        ])

        self.assertEqual([item.node_id for item in result.resolved], ["standard.ai"])
        self.assertEqual(result.resolved[0].match_type, "embedding")

    def test_invalid_bilingual_pair_never_reaches_embedder(self):
        resolver = self.make_resolver()
        fake = FakeEmbedder([])
        resolver._embedder = fake

        result = resolver.resolve_many([
            {
                "termino": "Seguridad de la información",
                "termino_en": "Seguridad de la información",
            }
        ])

        self.assertEqual(result.resolved, [])
        self.assertEqual(result.unresolved, ["Seguridad de la información"])
        self.assertEqual(fake.queries, [])

    def test_ambiguous_alias_is_not_accepted_as_exact_match(self):
        taxonomy = build_taxonomy()
        taxonomy.get_node("standard.ai").aliases.append("Shared alias")
        taxonomy.get_node("standard.programming").aliases = ["Shared alias"]
        taxonomy._build_indexes()
        resolver = self.make_resolver(taxonomy)
        resolver._embedder = FakeEmbedder([])

        result = resolver.resolve("Shared alias")

        self.assertIsNone(result)

    def test_real_source_catalog_resolves_tools_and_concepts(self):
        taxonomy = Taxonomy.from_file()
        resolver = self.make_resolver(taxonomy)
        resolver._embedder = FakeEmbedder([])

        expected = {
            "Docker": ("Docker", "onet_30_3"),
            "Kubernetes": ("Kubernetes", "cncf_glossary"),
            "Terraform": ("Terraform", "cncf_landscape"),
            "Ansible": ("Ansible", "esco_1_2_1"),
            "PyTorch": ("PyTorch", "cncf_landscape"),
            "Infrastructure as Code": (
                "Infrastructure as Code (IaC)",
                "cncf_glossary",
            ),
            "C": ("C", "cncf_landscape"),
            "C++": ("C++", "esco_1_2_1"),
            "SQL": ("SQL", "esco_1_2_1"),
        }

        for term, (node_name, source) in expected.items():
            with self.subTest(term=term):
                result = resolver.resolve(term)
                self.assertIsNotNone(result)
                self.assertEqual(result.node_name, node_name)
                self.assertEqual(taxonomy.get_node(result.node_id).source, source)

    def test_strips_curricular_wrapper_before_exact_resolution(self):
        resolver = self.make_resolver()

        result = resolver.resolve("Introduction to enterprise architecture")

        self.assertIsNotNone(result)
        self.assertEqual(result.node_id, "standard.enterprise_architecture")
        self.assertIn("curricular_wrapper", result.match_type)

    def test_strips_curricular_suffix_before_resolution(self):
        resolver = self.make_resolver()

        result = resolver.resolve("Enterprise architecture components")

        self.assertIsNotNone(result)
        self.assertEqual(result.node_id, "standard.enterprise_architecture")
        self.assertIn("curricular_wrapper", result.match_type)

    def test_resolves_dominant_contained_concept(self):
        resolver = self.make_resolver()

        result = resolver.resolve("Advanced enterprise architecture design")

        self.assertIsNotNone(result)
        self.assertEqual(result.node_id, "standard.enterprise_architecture")
        self.assertEqual(result.match_type, "contained_concept")

    def test_does_not_resolve_minor_concept_inside_long_activity(self):
        resolver = self.make_resolver()
        resolver._embedder = FakeEmbedder([])

        result = resolver.resolve(
            "Applications of ordinary differential equations in electrical circuits"
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
