import json

import httpx
from openai import AsyncOpenAI

from hanbit_assistant.agent import ChatSession
from hanbit_assistant.config import Settings


async def test_real_framework_request_fits_gateway_token_limit():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "resp_1",
                "object": "response",
                "created_at": 1,
                "model": "gpt-5.6-terra",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "id": "msg_1",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": "hello", "annotations": []}],
                    }
                ],
            },
        )

    config = Settings(
        "https://test.net/agent-rag/openai/v1",
        "test-key",
        "https://test.net/agent-rag/search",
        "student01",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:  # noqa: SIM117
        async with AsyncOpenAI(
            base_url=config.openai_base_url, api_key="test-key", http_client=http
        ) as client:
            chat = ChatSession(config, openai_client=client)
            try:
                await chat.ask("hello")
            finally:
                await chat.close()
    assert bodies
    assert all(0 < body["max_output_tokens"] <= 1500 for body in bodies)
    assert all(body["store"] is False and "previous_response_id" not in body for body in bodies)
