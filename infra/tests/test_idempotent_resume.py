import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provision import Manifest


def test_owned_matching_resource_is_read_back_not_recreated(tmp_path):
    rid = "/subscriptions/test/resourceGroups/lab"
    existing = {"location": "Korea Central", "properties": {"provisioningState": "succeeded"}}

    class AzureStub:
        def get(self, *args, **kwargs):
            return existing

        def wait(self, *args, **kwargs):
            return existing

        def request(self, *args, **kwargs):
            raise AssertionError("An unchanged resource must not receive another PUT")

    manifest = Manifest.__new__(Manifest)
    manifest.path = tmp_path / "manifest.json"
    manifest.data = {"resources": [{"id": rid, "version": "v", "status": "pending"}]}
    assert manifest.put(AzureStub(), rid, "v", {"location": "koreacentral"}) == existing
    assert manifest.data["resources"][0]["status"] == "verified"
