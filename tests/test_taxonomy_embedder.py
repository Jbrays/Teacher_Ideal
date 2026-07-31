import os
import tempfile
import unittest

import numpy as np

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")

from backend.services.taxonomy_embedder import TaxonomyEmbedder
from backend.taxonomy.models import Taxonomy


class RecordingModel:
    def __init__(self):
        self.inputs = []

    def encode(self, inputs, **kwargs):
        self.inputs.append(inputs)
        count = len(inputs) if isinstance(inputs, list) else 1
        vectors = np.ones((count, 3), dtype=np.float32)
        return vectors if isinstance(inputs, list) else vectors[0]


class TaxonomyEmbedderFormatTests(unittest.TestCase):
    def build_taxonomy(self) -> Taxonomy:
        return Taxonomy.from_dict({
            "roots": [{
                "id": "root",
                "name": "Root",
                "type": "root",
                "source": "test",
                "children": [{
                    "id": "root.ai",
                    "name": "Artificial intelligence",
                    "type": "leaf",
                    "source": "test",
                }],
            }]
        })

    def test_uses_multilingual_e5_query_and_passage_prefixes(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            embedder = TaxonomyEmbedder(
                taxonomy=self.build_taxonomy(),
                model_name="fake-e5",
                cache_dir=cache_dir,
            )
            model = RecordingModel()
            embedder._model = model

            embedder.build_embeddings(force=True)
            embedder.encode_query("Machine learning")

        self.assertEqual(model.inputs[0], [
            "passage: Artificial intelligence | Context: Root"
        ])
        self.assertEqual(model.inputs[1], "query: Machine learning")


if __name__ == "__main__":
    unittest.main()
