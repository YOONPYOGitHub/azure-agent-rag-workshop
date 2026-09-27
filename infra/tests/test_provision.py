import importlib.util
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class ProvisionTests(unittest.TestCase):
    def test_environment_files_are_private_and_exactly_mapped(self):
        self.assertIsNotNone(importlib.util.find_spec("provision"))
        import provision as p
        from security import ATTENDEES

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "attendees"
            for name in ATTENDEES:
                p.write_attendee(
                    target, name, "https://unit.azure-api.net", "unit-only-not-real-key"
                )
            files = sorted(target.glob("*.env"))
            self.assertEqual(len(files), 11)
            self.assertEqual({x.stem for x in files}, set(ATTENDEES))
            for f in files:
                self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)
                env = dict(
                    line.split("=", 1)
                    for line in f.read_text().splitlines()
                    if line and not line.startswith("#")
                )
                self.assertEqual(env["AZURE_SEARCH_INDEX"], f.stem)
                self.assertEqual(
                    env["OPENAI_BASE_URL"], "https://unit.azure-api.net/agent-rag/openai/v1"
                )
                self.assertEqual(
                    env["AZURE_SEARCH_ENDPOINT"], "https://unit.azure-api.net/agent-rag/search"
                )
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o700)

    def test_default_dry_run_and_narrow_resource_plan(self):
        self.assertIsNotNone(importlib.util.find_spec("provision"))
        import provision as p

        args = p.parser().parse_args(
            [
                "--subscription",
                "00000000-0000-0000-0000-000000000001",
                "--foundry-rg",
                "shared",
                "--foundry-name",
                "foundry",
                "--apim-rg",
                "shared",
                "--apim-name",
                "gateway",
            ]
        )
        self.assertFalse(args.apply)
        self.assertEqual(args.embedding_sku, "Standard")
        a = p.resource_ids(args)
        self.assertIn("/resourceGroups/rg-agent-rag-workshop/", a["search"])
        self.assertTrue(a["api"].endswith("/apis/agent-rag-workshop"))
        self.assertNotEqual(a["foundry"], a["embedding"])
        self.assertEqual(p.resource_ids(args), a)
        self.assertNotIn(a["apim"], p.deletable_ids(a))
        self.assertNotIn(a["foundry"], p.deletable_ids(a))
        self.assertIn(a["embedding"], p.deletable_ids(a))

    def test_readback_handles_provider_normalization_not_security_drift(self):
        import provision as p

        p.assert_subset(
            {
                "properties": {
                    "apiType": "http",
                    "templateParameters": [{"name": "indexName", "type": "string"}],
                }
            },
            {
                "properties": {
                    "type": "http",
                    "templateParameters": [
                        {"name": "indexName", "type": "string", "description": None}
                    ],
                }
            },
        )
        with self.assertRaises(p.SafeError):
            p.assert_subset(
                {"properties": {"subscriptionRequired": True}},
                {"properties": {"subscriptionRequired": False}},
            )
        with self.assertRaises(p.SafeError):
            p.assert_subset(
                {"properties": {"apiType": "http"}}, {"properties": {"type": "websocket"}}
            )

    def test_dry_run_transport_refuses_writes_and_secrets(self):
        import provision as p

        azure = p.Azure("00000000-0000-0000-0000-000000000001")
        for method in ("PUT", "POST", "DELETE"):
            with self.assertRaises(p.SafeError):
                azure.request(method, "/anything", "2025-01-01")

    def test_standard_has_no_silent_global_fallback(self):
        self.assertIsNotNone(importlib.util.find_spec("provision"))
        import provision as p

        metadata = [
            {
                "model": {
                    "name": "text-embedding-3-small",
                    "version": "1",
                    "isDefaultVersion": True,
                },
                "skus": [{"name": "GlobalStandard"}],
            }
        ]
        with self.assertRaises(p.SafeError):
            p.embedding_version(metadata, "Standard")
        self.assertEqual(p.embedding_version(metadata, "GlobalStandard"), "1")


if __name__ == "__main__":
    unittest.main()
