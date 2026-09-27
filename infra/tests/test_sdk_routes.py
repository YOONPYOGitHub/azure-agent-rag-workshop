"""Capture real SDK-built requests before any network I/O (no fake Azure replies)."""

import sys
import unittest
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from azure.core.credentials import AzureKeyCredential
    from azure.core.pipeline.transport import HttpTransport
    from azure.search.documents import SearchClient
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import SearchIndex, SimpleField

    HAS_SDK = True
except ImportError:
    HAS_SDK = False


class Captured(Exception):
    pass


@unittest.skipUnless(
    HAS_SDK, "Run with uv run --with azure-search-documents for the SDK transport check"
)
class SDKRouteTests(unittest.TestCase):
    def test_actual_sdk_odata_requests_are_in_the_gateway_allowlist(self):
        from security import authorize_route

        class Capture(HttpTransport):
            def open(self):
                pass

            def close(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def send(self, request, **kwargs):
                self.request = request
                raise Captured()

        transport = Capture()
        endpoint = "https://unit.azure-api.net/agent-rag/search"
        credential = AzureKeyCredential("transport-capture-only")
        index = SearchIndexClient(endpoint, credential, transport=transport, retry_total=0)
        docs = SearchClient(endpoint, "student01", credential, transport=transport, retry_total=0)
        calls = [
            lambda: index.get_index("student01"),
            lambda: index.create_or_update_index(
                SearchIndex(
                    name="student01", fields=[SimpleField(name="id", type="Edm.String", key=True)]
                )
            ),
            lambda: docs.upload_documents([{"id": "one"}]),
            lambda: list(docs.search("hello")),
            lambda: docs.get_document_count(),
        ]
        for call in calls:
            with self.assertRaises(Captured):
                call()
            request = transport.request
            path = urlsplit(request.url).path.removeprefix("/agent-rag")
            self.assertTrue(
                authorize_route("student01", request.method, path), (request.method, path)
            )
            self.assertFalse(authorize_route("student02", request.method, path))


if __name__ == "__main__":
    unittest.main()
