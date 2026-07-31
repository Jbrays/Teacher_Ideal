import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")

from backend.llm.client import GeminiClient


class GeminiJsonParserTests(unittest.TestCase):
    def test_accepts_json_with_duplicated_closing_delimiter(self):
        result = GeminiClient._parse_json('{"value": 1}}')

        self.assertEqual(result, {"value": 1})

    def test_rejects_non_structural_trailing_content(self):
        with self.assertRaises(ValueError):
            GeminiClient._parse_json('{"value": 1} trailing text')


if __name__ == "__main__":
    unittest.main()
