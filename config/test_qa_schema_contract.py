from pathlib import Path

from django.test import SimpleTestCase

from config.schema import schema


class SchemaContractTests(SimpleTestCase):
    snapshot_path = Path(__file__).with_name("schema.snapshot.graphql")

    def test_schema_snapshot_matches_generated_schema(self):
        self.assertTrue(self.snapshot_path.exists())
        self.assertEqual(str(schema), self.snapshot_path.read_text(encoding="utf-8"))

    def test_schema_keeps_client_critical_roots(self):
        schema_text = str(schema)
        for field in (
            "type Query",
            "type Mutation",
            "me:",
            "tokenAuth(",
            "refreshToken(",
            "deleteTokenCookie:",
            "deleteRefreshTokenCookie:",
        ):
            self.assertIn(field, schema_text)
