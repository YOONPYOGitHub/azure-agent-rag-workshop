"""Offline regressions for abstention-prefixed model output."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import AsyncOpenAI
from test_agent import function, message, response, settings

from hanbit_assistant.agent import UNKNOWN_POLICY, ChatSession
from hanbit_assistant.experiments import BaselineSession


@pytest.mark.parametrize("session_kind", ["rag", "agent"])
@pytest.mark.parametrize(
    "model_text",
    [
        "제공된 문서에서 확인할 수 없습니다",
        UNKNOWN_POLICY,
        "제공된 문서에서 확인할 수 없습니다. 보너스 100만원 지급",
        "제공된 문서에서 확인할 수 없습니다. 보너스 100만원 지급 [known]",
        "제공된 문서에서 확인할 수 없습니다. 보너스 100만원 지급 [invented]",
        " \n\t제공된 문서에서 확인할 수 없습니다. 보너스 100만원 지급 [known] [invented]",
    ],
    ids=["pure", "canonical", "uncited-claim", "known-id", "unknown-id", "mixed-whitespace"],
)
async def test_leading_abstention_is_normalized(session_kind, model_text):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        output = (
            [function("search_policy", {"query": "보너스 규정"})]
            if session_kind == "agent" and calls == 1
            else [message(model_text)]
        )
        return httpx.Response(200, json=response(output, calls))

    rows = [{"id": "known", "citation": "[known]", "content": "출장 시 팀장 승인"}]
    policy = SimpleNamespace(search=AsyncMock(return_value=rows))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        api = AsyncOpenAI(base_url=settings().openai_base_url, api_key="x", http_client=http)
        if session_kind == "agent":
            session = ChatSession(settings(), openai_client=api, policy_search=policy)
        else:
            session = BaselineSession(
                settings(), mode="rag", openai_client=api, policy_search=policy
            )
        try:
            turn = await session.ask("보너스 규정은?")
        finally:
            await session.close()

    assert turn.text == UNKNOWN_POLICY
    assert "invented" not in turn.text
    assert "100만원" not in turn.text
    assert "근거 인용" not in turn.text
    assert turn.sources == rows
    policy.search.assert_awaited_once()
