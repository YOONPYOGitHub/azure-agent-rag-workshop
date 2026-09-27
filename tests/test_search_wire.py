"""실제 Azure SDK가 생성하는 APIM 경로/헤더를 외부 전송 직전에 검증합니다."""

import json

from azure.core.pipeline.transport import AsyncHttpResponse, AsyncHttpTransport

from hanbit_assistant.clients import create_index_client, create_search_client
from hanbit_assistant.config import Settings
from hanbit_assistant.search import build_index


class Response(AsyncHttpResponse):
    def __init__(self, request, body):
        super().__init__(request, None)
        self.status_code = 200
        self.headers = {"content-type": "application/json"}
        self.content_type = "application/json"
        self._body = json.dumps(body).encode()

    def body(self):
        return self._body

    async def load_body(self):
        pass


class Transport(AsyncHttpTransport):
    def __init__(self):
        self.requests = []

    async def open(self):
        pass

    async def close(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def send(self, request, **kwargs):
        self.requests.append(request)
        if request.method == "PUT":
            return Response(request, build_index("student01").serialize())
        return Response(request, {"value": []})


async def test_real_search_sdk_preserves_apim_prefix_and_both_headers():
    settings = Settings(
        "https://a.net/agent-rag/openai/v1",
        "test-key",
        "https://a.net/agent-rag/search",
        "student01",
    )
    search, index = create_search_client(settings), create_index_client(settings)
    search_transport, index_transport = Transport(), Transport()
    # Replace only the network transport; all SDK serialization/policies run unchanged.
    search._client._client._pipeline._transport.send = search_transport.send
    index._client._client._pipeline._transport.send = index_transport.send
    results = await search.search(search_text="출장", top=1)
    assert [row async for row in results] == []
    await index.create_or_update_index(build_index("student01"))
    for request in search_transport.requests + index_transport.requests:
        assert request.url.startswith("https://a.net/agent-rag/search/")
        assert request.headers["Ocp-Apim-Subscription-Key"] == "test-key"
        assert request.headers["api-key"] == "test-key"
        assert "student01" in request.url
    assert "/docs/search.post.search" in search_transport.requests[0].url
    await search.close()
    await index.close()
