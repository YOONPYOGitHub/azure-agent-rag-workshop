import xml.etree.ElementTree as ET
from pathlib import Path


def test_auth_route_and_throttle_errors_are_not_masked_as_bad_input():
    p = Path(__file__).resolve().parents[1] / "apim-policy.xml.tpl"
    root = ET.fromstring(p.read_text().replace("{{DENY_ROUTE}}", "false"))
    codes = {n.attrib["code"] for n in root.findall("./on-error//set-status")}
    assert {"401", "404", "429", "400"} <= codes
