import xml.etree.ElementTree as ET
from pathlib import Path


def test_api_scope_does_not_emit_product_only_quota_policy():
    p = Path(__file__).resolve().parents[1] / "apim-policy.xml.tpl"
    root = ET.fromstring(p.read_text().replace("{{DENY_ROUTE}}", "false"))
    assert root.find("./inbound/quota") is None
    assert root.find("./inbound/rate-limit") is not None
