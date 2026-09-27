import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest


async def test_explicit_abstention_is_preserved_with_irrelevant_candidates():
    from hanbit_assistant.agent import ChatSession

    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        output = (
            [function("search_policy", {"query": "없는 보너스 규정"})]
            if calls == 1
            else [
                message(
                    "제공된 문서에서 확인할 수 없습니다. 검색된 출장 사규에는 보너스 규정이 없습니다."
                )
            ]
        )
        return httpx.Response(200, json=response(output, calls))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        api = AsyncOpenAI(base_url=settings().openai_base_url, api_key="x", http_client=http)
        policy = SimpleNamespace(
            search=AsyncMock(
                return_value=[
                    {
                        "id": "abc",
                        "citation": "[abc]",
                        "source": "data/policies/a.md",
                        "content": "출장 시 팀장 승인",
                        "title": "출장",
                        "section": "승인",
                        "page": 1,
                    }
                ]
            )
        )
        chat = ChatSession(settings(), openai_client=api, policy_search=policy)
        turn = await chat.ask("보너스 규정은?")
        assert turn.text.startswith("제공된 문서에서 확인할 수 없습니다")
        assert "근거 인용" not in turn.text
        assert len(turn.sources) == 1
        await chat.close()


async def test_session_has_a_bounded_conversation_budget():
    from hanbit_assistant.agent import AssistantError, ChatSession

    def handler(request):
        return httpx.Response(200, json=response([message("안녕")]))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        api = AsyncOpenAI(base_url=settings().openai_base_url, api_key="x", http_client=http)
        chat = ChatSession(settings(), openai_client=api)
        for _ in range(20):
            await chat.ask("안녕")
        with pytest.raises(AssistantError, match="20"):
            await chat.ask("한 번 더")
        chat.reset()
        assert (await chat.ask("새 대화")).text == "안녕"
        await chat.close()


async def test_mixed_valid_and_invented_citations_are_rejected():
    from hanbit_assistant.agent import ChatSession

    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json=response(
                [function("search_policy", {"query": "규정"})]
                if calls == 1
                else [message("맞는 인용 [abc] 틀린 인용 [deadbeef]")],
                calls,
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        api = AsyncOpenAI(base_url=settings().openai_base_url, api_key="x", http_client=http)
        policy = SimpleNamespace(
            search=AsyncMock(
                return_value=[
                    {
                        "id": "abc",
                        "citation": "[abc]",
                        "source": "data/policies/a.md",
                        "content": "규정",
                        "title": "A",
                        "section": "A",
                        "page": 1,
                    }
                ]
            )
        )
        chat = ChatSession(settings(), openai_client=api, policy_search=policy)
        turn = await chat.ask("규정")
        assert "deadbeef" not in turn.text
        await chat.close()


async def test_agent_timeouts_are_safe_and_discard_partial_history():
    from hanbit_assistant.agent import AssistantError, ChatSession

    async def handler(request):
        await asyncio.sleep(0.2)
        return httpx.Response(200, json=response([message("late")]))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        api = AsyncOpenAI(
            base_url=settings().openai_base_url, api_key="test-secret", http_client=http
        )
        chat = ChatSession(settings(timeout_seconds=0.01), openai_client=api)
        old = chat.session.session_id
        with pytest.raises(AssistantError, match="시간") as exc:
            await chat.ask("시간 초과")
        assert "test-secret" not in str(exc.value)
        assert chat.session.session_id != old
        await chat.close()


async def test_agent_rejects_long_blank_inputs_and_bounds_actual_tool_calls():
    from hanbit_assistant.agent import AssistantError, ChatSession

    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json=response([function("search_policy", {"query": "계속"}, f"call_{calls}")], calls),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        api = AsyncOpenAI(base_url=settings().openai_base_url, api_key="x", http_client=http)
        policy = SimpleNamespace(search=AsyncMock(return_value=[]))
        chat = ChatSession(settings(max_tool_calls=2), openai_client=api, policy_search=policy)
        for bad in [" ", "x" * 4001]:
            with pytest.raises(AssistantError):
                await chat.ask(bad)
        assert calls == 0
        try:
            await chat.ask("계속 검색해")
        except AssistantError:
            pass
        assert policy.search.await_count <= 2
        assert len(chat.tool_events) <= 2
        assert calls <= 4
        await chat.close()


async def test_agent_rejects_uncited_policy_answer_and_does_not_leak_sdk_error():
    from hanbit_assistant.agent import AssistantError, ChatSession

    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls > 2:
            return httpx.Response(
                401,
                json={"error": {"message": "test-secret raw url", "type": "authentication_error"}},
            )
        return httpx.Response(
            200,
            json=response(
                [function("search_policy", {"query": "규정"})]
                if calls == 1
                else [message("근거 없는 답변 [invented]")],
                calls,
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        api = AsyncOpenAI(
            base_url=settings().openai_base_url, api_key="x", http_client=http, max_retries=0
        )
        policy = SimpleNamespace(
            search=AsyncMock(
                return_value=[
                    {
                        "id": "abc",
                        "citation": "[abc]",
                        "source": "data/policies/a.md",
                        "content": "규정",
                        "title": "A",
                        "section": "A",
                        "page": 1,
                    }
                ]
            )
        )
        chat = ChatSession(settings(), openai_client=api, policy_search=policy)
        turn = await chat.ask("규정")
        assert "invented" not in turn.text
        assert "인용" in turn.text
        with pytest.raises(AssistantError) as exc:
            await chat.ask("오류")
        assert "test-secret" not in str(exc.value)
        await chat.close()


from openai import AsyncOpenAI

from hanbit_assistant.config import Settings


def settings(**kwargs):
    return Settings(
        "https://a.net/agent-rag/openai/v1",
        "test-secret",
        "https://a.net/agent-rag/search",
        "student01",
        **kwargs,
    )


def response(output, number=1):
    return {
        "id": f"resp_{number}",
        "object": "response",
        "created_at": 1,
        "model": "gpt-5.6-terra",
        "status": "completed",
        "output": output,
        "parallel_tool_calls": False,
        "tool_choice": "auto",
    }


def message(text):
    return {
        "id": "msg_1",
        "type": "message",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def function(name, arguments, call_id="call_1"):
    return {
        "type": "function_call",
        "id": "fc_1",
        "call_id": call_id,
        "name": name,
        "arguments": json.dumps(arguments),
        "status": "completed",
    }


async def test_real_agent_responses_tool_loop_returns_citations_and_safe_trace():
    from agent_framework import Agent
    from agent_framework_openai import OpenAIChatClient

    from hanbit_assistant.agent import ChatSession
    from hanbit_assistant.agent import OpenAIChatClient as WorkshopClient

    assert WorkshopClient is OpenAIChatClient
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.url.path == "/agent-rag/openai/v1/responses"
        assert body["model"] == "gpt-5.6-terra"
        assert body["store"] is False
        output = (
            [function("search_policy", {"query": "도쿄 숙박"})]
            if len(requests) == 1
            else [message("숙박 규정입니다. [abc123]")]
        )
        return httpx.Response(200, json=response(output, len(requests)))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        api = AsyncOpenAI(
            base_url=settings().openai_base_url, api_key="test-secret", http_client=http
        )
        policy = SimpleNamespace(
            search=AsyncMock(
                return_value=[
                    {
                        "id": "abc123",
                        "citation": "[abc123]",
                        "source": "data/policies/a.md",
                        "content": "규정 내용",
                        "title": "출장",
                        "section": "숙박",
                        "page": 1,
                    }
                ]
            )
        )
        chat = ChatSession(settings(), openai_client=api, policy_search=policy)
        assert isinstance(chat.agent, Agent)
        turn = await chat.ask("도쿄 출장 숙박 규정은?")
        assert "[abc123]" in turn.text
        assert turn.sources[0]["id"] == "abc123"
        assert turn.tool_events[0]["tool"] == "search_policy"
        assert turn.tool_events[0]["status"] == "ok"
        assert "test-secret" not in str(turn.tool_events)
        assert {t["name"] for t in requests[0]["tools"]} == {
            "search_policy",
            "get_weather",
            "convert_currency",
        }
        assert any(i["type"] == "function_call_output" for i in requests[1]["input"])
        await chat.close()


async def test_sessions_are_isolated_and_reset_discards_history():
    from hanbit_assistant.agent import ChatSession

    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=response([message("안녕하세요.")], len(requests)))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        api = AsyncOpenAI(base_url=settings().openai_base_url, api_key="x", http_client=http)
        a = ChatSession(settings(), openai_client=api)
        b = ChatSession(settings(), openai_client=api)
        assert a.session.session_id != b.session.session_id
        await a.ask("내 이름은 민수")
        await a.ask("내 이름은?")
        assert "민수" in json.dumps(requests[-1], ensure_ascii=False)
        await b.ask("안녕")
        assert "민수" not in json.dumps(requests[-1], ensure_ascii=False)
        previous = a.session.session_id
        a.reset()
        assert a.session.session_id != previous
        await a.ask("다시 시작")
        assert "민수" not in json.dumps(requests[-1], ensure_ascii=False)
        await a.close()
        await b.close()


async def test_empty_search_refuses_unknown_policy():
    from hanbit_assistant.agent import ChatSession

    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json=response(
                [function("search_policy", {"query": "없는 규정"})]
                if calls == 1
                else [message("보너스 100만원 지급")],
                calls,
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        api = AsyncOpenAI(base_url=settings().openai_base_url, api_key="x", http_client=http)
        chat = ChatSession(
            settings(),
            openai_client=api,
            policy_search=SimpleNamespace(search=AsyncMock(return_value=[])),
        )
        turn = await chat.ask("없는 규정")
        assert "확인할 수 없습니다" in turn.text
        assert "100만원" not in turn.text
        assert turn.sources == []
        await chat.close()
