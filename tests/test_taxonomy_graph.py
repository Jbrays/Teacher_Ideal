import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")

from backend.taxonomy.models import Taxonomy
from backend.taxonomy.resolver import TaxonomyResolver


class TaxonomyGraphUnitTests(unittest.TestCase):
    def build_taxonomy(self) -> Taxonomy:
        return Taxonomy.from_dict({
            "version": "test",
            "roots": [
                {
                    "id": "source_a",
                    "name": "Source A",
                    "type": "root",
                    "source": "test_a",
                    "children": [
                        {
                            "id": "source_a.parent",
                            "name": "Parent",
                            "type": "branch",
                            "source": "test_a",
                            "children": [
                                {
                                    "id": "source_a.one",
                                    "name": "One",
                                    "type": "leaf",
                                    "source": "test_a",
                                },
                                {
                                    "id": "source_a.two",
                                    "name": "Two",
                                    "type": "leaf",
                                    "source": "test_a",
                                },
                            ],
                        },
                        {
                            "id": "source_a.unrelated",
                            "name": "Unrelated",
                            "type": "leaf",
                            "source": "test_a",
                        },
                    ],
                },
                {
                    "id": "source_b",
                    "name": "Source B",
                    "type": "root",
                    "source": "test_b",
                    "children": [
                        {
                            "id": "source_b.one",
                            "name": "One",
                            "type": "leaf",
                            "source": "test_b",
                        },
                        {
                            "id": "source_b.example",
                            "name": "Example product",
                            "type": "leaf",
                            "source": "test_b",
                        },
                    ],
                },
            ],
            "relations": [
                {
                    "source_id": "source_a.one",
                    "target_id": "source_b.one",
                    "relation_type": "exact_label_match",
                    "weight": 0.97,
                },
                {
                    "source_id": "source_a.parent",
                    "target_id": "source_b.example",
                    "relation_type": "official_alias_reference",
                    "weight": 0.78,
                },
            ],
        })

    def test_hierarchy_is_weighted_but_root_is_not_semantic(self):
        taxonomy = self.build_taxonomy()

        self.assertEqual(
            taxonomy.semantic_similarity("source_a.one", "source_a.parent"),
            0.72,
        )
        self.assertEqual(
            taxonomy.semantic_similarity("source_a.one", "source_a.two"),
            0.518,
        )
        self.assertEqual(
            taxonomy.semantic_similarity(
                "source_a.one",
                "source_a.unrelated",
            ),
            0.0,
        )

    def test_canonical_cross_source_matches_are_full_equivalence(self):
        taxonomy = self.build_taxonomy()

        self.assertTrue(
            taxonomy.are_equivalent(["source_a.one", "source_b.one"])
        )
        self.assertEqual(
            taxonomy.semantic_similarity("source_a.one", "source_b.one"),
            1.0,
        )

    def test_official_alias_reference_is_related_not_equivalent(self):
        taxonomy = self.build_taxonomy()

        self.assertFalse(
            taxonomy.are_equivalent(
                ["source_a.parent", "source_b.example"]
            )
        )
        self.assertEqual(
            taxonomy.semantic_similarity(
                "source_a.parent",
                "source_b.example",
            ),
            0.78,
        )


class RealTaxonomyCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.taxonomy = Taxonomy.from_file()
        cls.resolver = TaxonomyResolver(
            cls.taxonomy,
            fuzzy_threshold=0.95,
        )

    def test_catalog_contains_all_pinned_sources(self):
        source_ids = {source["id"] for source in self.taxonomy.sources}

        self.assertEqual(self.taxonomy.version, "3.0.0")
        self.assertTrue({
            "acm_ccs_2012",
            "sfia_9",
            "itil_4",
            "esco_1_2_1",
            "cso_3_5",
            "cncf_glossary",
            "cncf_landscape",
            "onet_30_3",
        }.issubset(source_ids))

    def test_product_alias_does_not_become_concept_equivalence(self):
        zoom_nodes = self.taxonomy.get_nodes_by_alias("Zoom")
        esco = next(node for node in zoom_nodes if node.source == "esco_1_2_1")
        onet = next(node for node in zoom_nodes if node.source == "onet_30_3")

        self.assertFalse(self.taxonomy.are_equivalent([esco.id, onet.id]))
        self.assertEqual(
            self.taxonomy.semantic_similarity(esco.id, onet.id),
            0.78,
        )

    def test_same_official_product_across_sources_is_equivalent(self):
        nodes = self.taxonomy.get_nodes_by_alias("Kubernetes")
        node_ids = [node.id for node in nodes]

        self.assertGreaterEqual(len(node_ids), 3)
        self.assertTrue(self.taxonomy.are_equivalent(node_ids))
        self.assertEqual(
            self.taxonomy.semantic_similarity(node_ids[0], node_ids[-1]),
            1.0,
        )

    def test_unrelated_exact_only_products_are_not_connected_by_root(self):
        docker = self.resolver.resolve("Docker")
        zoom = self.resolver.resolve("Zoom")

        self.assertIsNotNone(docker)
        self.assertIsNotNone(zoom)
        self.assertEqual(
            self.taxonomy.semantic_similarity(docker.node_id, zoom.node_id),
            0.0,
        )

    def test_landscape_siblings_do_not_imply_coverage(self):
        terraform = next(
            node
            for node in self.taxonomy.get_nodes_by_alias("Terraform")
            if node.source == "cncf_landscape"
        )
        ansible = next(
            node
            for node in self.taxonomy.get_nodes_by_alias("Ansible")
            if node.source == "cncf_landscape"
        )

        self.assertEqual(terraform.parent_id, ansible.parent_id)
        self.assertLess(
            self.taxonomy.semantic_similarity(terraform.id, ansible.id),
            0.55,
        )


if __name__ == "__main__":
    unittest.main()
