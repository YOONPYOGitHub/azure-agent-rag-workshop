import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TeardownTests(unittest.TestCase):
    def test_manifest_cleanup_rejects_shared_or_injected_resources(self):
        self.assertIsNotNone(importlib.util.find_spec("teardown"))
        import provision as p
        import teardown as t

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
        ids = p.resource_ids(args)
        config = {
            k: v
            for k, v in vars(args).items()
            if k not in {"apply", "dry_run", "manifest", "attendee_dir"}
        }
        manifest = {
            "schema": 1,
            "owner": p.OWNER,
            "ids": ids,
            "config": config,
            "resources": [{"id": ids["rg"], "version": p.RG_VERSION}],
        }
        self.assertEqual(t.cleanup_plan(manifest), [(ids["rg"], p.RG_VERSION)])
        for rid in [
            ids["foundry"],
            ids["apim"],
            ids["api"] + "-other",
            ids["search"] + "/providers/Microsoft.Authorization/roleAssignments/random",
        ]:
            manifest["resources"].append({"id": rid, "version": p.APIM_VERSION})
            with self.assertRaises(p.SafeError):
                t.cleanup_plan(manifest)
            manifest["resources"].pop()


if __name__ == "__main__":
    unittest.main()
