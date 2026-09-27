import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provision import Azure


def test_policy_readback_accepts_azure_raw_xml_with_bom():
    sub = "00000000-0000-0000-0000-000000000001"
    rid = f"/subscriptions/{sub}/resourceGroups/lab/providers/Microsoft.ApiManagement/service/lab/apis/lab/policies/policy"
    output = "\ufeff<policies><inbound /></policies>"
    with patch(
        "provision.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout=output, stderr=""),
    ):
        result = Azure(sub).get(rid, "2024-05-01")
    assert result["properties"]["value"] == output.lstrip("\ufeff")
