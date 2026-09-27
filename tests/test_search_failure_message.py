from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from openai import AsyncOpenAI
from test_agent import function, message, response, settings

from hanbit_assistant.agent import ChatSession


async def test_search_service_failure_is_not_reported_as_missing_policy():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        items = (
            [function("search_policy", {"query": "도쿄"})]
            if calls == 1
            else [message("검색에 실패했습니다.")]
        )
        return httpx.Response(200, json=response(items, calls))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        api = AsyncOpenAI(base_url=settings().openai_base_url, api_key="test", http_client=http)
        policy = SimpleNamespace(search=AsyncMock(side_effect=RuntimeError("private-secret")))
        chat = ChatSession(settings(), openai_client=api, policy_search=policy)
        try:
            result = await chat.ask("규정 질문")
        finally:
            await chat.close()
        assert "검색 서비스" in result.text
        assert "제공된 문서에서 확인할 수 없습니다" not in result.text
        assert "private-secret" not in result.text
        assert result.tool_events[0]["status"] == "error"
