import xml.etree.ElementTree as ET
from pathlib import Path


def test_search_rewrite_uses_original_path_after_backend_selection():
    p = Path(__file__).resolve().parents[1] / "apim-policy.xml.tpl"
    root = ET.fromstring(p.read_text().replace("{{DENY_ROUTE}}", "false"))
    routes = [n.attrib["template"] for n in root.findall(".//rewrite-uri")]
    search_route = next(v for v in routes if "/agent-rag/search" in v)
    assert "context.Request.OriginalUrl.Path" in search_route
