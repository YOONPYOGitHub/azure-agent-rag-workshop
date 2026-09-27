import xml.etree.ElementTree as ET
from pathlib import Path


def test_search_vectors_have_a_larger_body_budget_than_model_prompts():
    template = Path(__file__).resolve().parents[1] / "apim-policy.xml.tpl"
    root = ET.fromstring(template.read_text().replace("{{DENY_ROUTE}}", "false"))
    guards = [node.attrib["condition"] for node in root.findall(".//when")]
    body_guard = next(text for text in guards if "GetByteCount" in text)
    assert "2097152" in body_guard  # 16 documents × 1536 float32 values fit.
    assert "262144" in body_guard  # Model route retains its smaller upper bound.
    assert "context.Operation.Id" in body_guard
