"""Offline boundary tests; fixtures are not live Azure evidence."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import AsyncOpenAI

from hanbit_assistant import agent, experiments
from hanbit_assistant.config import Settings


def settings():
    return Settings("https://a.net/openai/v1", "secret-test", "https://a.net/search", "student01")


async def test_plain_mode_has_no_tools_no_search_no_remote_history():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "resp_fixture",
                "object": "response",
                "created_at": 1,
                "model": "gpt-5.6-terra",
                "status": "completed",
                "output": [
                    {
                        "id": "msg_fixture",
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "일반 설명", "annotations": []}
                        ],
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        api = AsyncOpenAI(
            api_key="secret-test", http_client=http, base_url=settings().openai_base_url
        )
        policy = SimpleNamespace(search=AsyncMock(side_effect=AssertionError("must not search")))
        session = experiments.BaselineSession(
            settings(), mode="plain", openai_client=api, policy_search=policy
        )
        result = await session.ask("출장 규정은?")
        await session.ask("새 질문")
        assert result.text == "일반 설명"
        assert result.sources == []
        assert not policy.search.called
        assert all(not r.get("tools") and r["store"] is False for r in requests)
        assert "출장 규정은?" not in json.dumps(requests[-1]["input"], ensure_ascii=False)
        await session.close()


async def test_rag_retrieves_selected_mode_then_generates_with_only_evidence():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "resp_fixture",
                "object": "response",
                "created_at": 1,
                "model": "gpt-5.6-terra",
                "status": "completed",
                "output": [
                    {
                        "id": "msg_fixture",
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "팀장 승인 [approval-1]",
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        )

    rows = [
        {
            "id": "approval-1",
            "citation": "[approval-1]",
            "content": "팀장 승인 필요",
            "source": "data/policies/01_scope_approval.md",
            "title": "승인",
            "section": "승인",
            "page": 1,
        }
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        api = AsyncOpenAI(
            api_key="secret-test", http_client=http, base_url=settings().openai_base_url
        )
        policy = SimpleNamespace(search=AsyncMock(return_value=rows))
        session = experiments.BaselineSession(
            settings(), mode="rag", search_mode="keyword", openai_client=api, policy_search=policy
        )
        result = await session.ask("승인은?")
        policy.search.assert_awaited_once_with("승인은?", mode="keyword", top=5)
        assert result.sources == rows
        assert result.text == "팀장 승인 [approval-1]"
        assert not requests[0].get("tools")
        assert "팀장 승인 필요" in str(requests[0]["input"])
        assert [e["tool"] for e in result.tool_events] == ["search_policy", "model_response"]
        await session.close()


async def test_empty_rag_skips_generation_and_never_invents_policy():
    api = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(side_effect=AssertionError("no evidence")))
    )
    policy = SimpleNamespace(search=AsyncMock(return_value=[]))
    session = experiments.BaselineSession(
        settings(), mode="rag", openai_client=api, policy_search=policy
    )
    result = await session.ask("없는 정책")
    assert result.text.startswith("제공된 문서에서 확인할 수 없습니다")
    assert not api.responses.create.called
    await session.close()


async def test_rag_rejects_invented_citation_and_redacts_provider_exception():
    import pytest

    from hanbit_assistant.agent import AssistantError

    api = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(return_value=SimpleNamespace(output_text="사규 [invented]"))
        )
    )
    policy = SimpleNamespace(
        search=AsyncMock(return_value=[{"id": "known", "citation": "[known]", "content": "규정"}])
    )
    session = experiments.BaselineSession(
        settings(), mode="rag", openai_client=api, policy_search=policy
    )
    result = await session.ask("규정은?")
    assert "invented" not in result.text
    assert "인용" in result.text
    policy.search.side_effect = RuntimeError("secret-test")
    with pytest.raises(AssistantError) as error:
        await session.ask("규정은?")
    assert "secret-test" not in str(error.value)
    api.responses.create.assert_awaited_once()
    await session.close()


@pytest.mark.parametrize("session_kind", ["rag", "agent"])
@pytest.mark.parametrize("owns_openai", [True, False], ids=["owned-openai", "injected-openai"])
@pytest.mark.parametrize("owns_search", [True, False], ids=["owned-search", "injected-search"])
@pytest.mark.parametrize("search_fails", [False, True], ids=["search-ok", "search-fails"])
async def test_close_attempts_all_owned_clients(
    monkeypatch, session_kind, owns_openai, owns_search, search_fails
):
    attempts = []

    class Client:
        def __init__(self, name, fails=False):
            self.name = name
            self.fails = fails

        async def close(self):
            attempts.append(self.name)
            if self.fails:
                raise RuntimeError("search close failed")

    api = Client("openai")
    policy = Client("search", fails=search_fails)
    module = experiments if session_kind == "rag" else agent
    monkeypatch.setattr(module, "create_openai_client", lambda settings: api)
    monkeypatch.setattr(module, "PolicySearch", lambda settings, openai_client: policy)
    monkeypatch.setattr(
        agent, "create_agent", lambda *args: SimpleNamespace(create_session=lambda: object())
    )
    kwargs = {
        "openai_client": None if owns_openai else api,
        "policy_search": None if owns_search else policy,
    }
    if session_kind == "rag":
        session = experiments.BaselineSession(settings(), mode="rag", **kwargs)
    else:
        session = agent.ChatSession(settings(), **kwargs)

    if owns_search and search_fails:
        with pytest.raises(RuntimeError, match="search close failed"):
            await session.close()
    else:
        await session.close()

    expected = []
    if owns_search:
        expected.append("search")
    if owns_openai:
        expected.append("openai")
    assert attempts == expected
