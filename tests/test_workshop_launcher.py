"""Offline launcher tests: never load the developer's .env or contact Azure."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENV_NAMES = (
    "WORKSHOP_API_KEY",
    "OPENAI_BASE_URL",
    "AZURE_SEARCH_ENDPOINT",
    "AZURE_SEARCH_INDEX",
    "OPENAI_MODEL",
    "AZURE_SEARCH_SEMANTIC",
    "CODESPACES",
)


@pytest.fixture
def launcher(monkeypatch):
    path = ROOT / "scripts/workshop.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("workshop_launcher", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    return module


def test_missing_configuration_is_nonzero_and_explained_in_korean(launcher, capsys):
    assert launcher is not None, "The workshop launcher has not been implemented"
    assert launcher.main(["doctor"]) != 0
    output = capsys.readouterr().out
    assert "로컬" in output
    assert "설정" in output
    assert ".env.example" in output
    for name in ENV_NAMES[:4]:
        assert name in output


@pytest.mark.parametrize("codespaces,label", [("true", "Codespaces"), ("false", "로컬")])
def test_offline_doctor_is_network_free_and_detects_environment(
    configured, monkeypatch, capsys, codespaces, label
):
    import socket

    def no_network(*args, **kwargs):
        pytest.fail("offline doctor opened a socket")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setenv("CODESPACES", codespaces)
    assert configured.main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert label in output
    assert "오프라인 점검 완료" in output
    assert "test-secret-never-display" not in output


def test_missing_dependency_has_install_instruction(configured, monkeypatch, capsys):
    import importlib.metadata

    def absent(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", absent)
    assert configured.main(["doctor"]) == 1
    output = capsys.readouterr().out
    assert "의존성" in output
    assert "uv sync --frozen" in output


@pytest.fixture
def fake_live(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from hanbit_assistant import clients

    model = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(return_value=SimpleNamespace(output_text="READY"))
        ),
        close=AsyncMock(),
    )
    model.with_options = Mock(return_value=model)
    index = SimpleNamespace(get_index=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(clients, "create_openai_client", lambda settings: model)
    monkeypatch.setattr(clients, "create_index_client", lambda settings: index)
    return model, index


def test_live_checks_only_ready_and_own_index(configured, fake_live, capsys):
    model, index = fake_live
    assert configured.main(["doctor", "--live"]) == 0
    request = model.responses.create.call_args.kwargs
    assert request["store"] is False
    assert 1 <= request["max_output_tokens"] <= 64
    assert request["input"] == "Reply with exactly READY."
    assert "tools" not in request
    assert model.with_options.call_args.kwargs["max_retries"] == 0
    index.get_index.assert_awaited_once_with("student01", retry_total=0)
    model.close.assert_awaited_once()
    index.close.assert_awaited_once()
    output = capsys.readouterr().out
    assert "READY" in output
    assert "본인 Search 인덱스" in output
    assert "test-secret-never-display" not in output


@pytest.mark.parametrize("failure", ["model", "search", "unexpected-response"])
def test_live_failure_redacts_sdk_errors_and_closes_clients(configured, fake_live, capsys, failure):
    import logging
    from types import SimpleNamespace

    model, index = fake_live
    secret = "secret-from-sdk-response"

    async def fail(*args, **kwargs):
        logging.getLogger("openai").error(secret)
        raise RuntimeError(secret)

    if failure == "model":
        model.responses.create.side_effect = fail
    elif failure == "search":
        index.get_index.side_effect = fail
    else:
        model.responses.create.return_value = SimpleNamespace(output_text=secret)
    assert configured.main(["doctor", "--live"]) == 1
    output = capsys.readouterr()
    assert secret not in output.out + output.err
    assert "실시간 점검 실패" in output.out
    assert "인덱스" in output.out
    model.close.assert_awaited_once()
    index.close.assert_awaited_once()


def test_live_deadline_is_bounded(configured, fake_live, monkeypatch, capsys):
    import asyncio
    from types import SimpleNamespace

    async def slow(**kwargs):
        await asyncio.sleep(0.05)
        return SimpleNamespace(output_text="READY")

    fake_live[0].responses.create.side_effect = slow
    monkeypatch.setattr(configured, "LIVE_TIMEOUT_SECONDS", 0.001, raising=False)
    assert configured.main(["doctor", "--live"]) == 1
    assert "시간 제한" in capsys.readouterr().out
    fake_live[0].close.assert_awaited_once()
    fake_live[1].close.assert_awaited_once()


@pytest.mark.parametrize("failure", ["error", "slow"])
def test_live_cleanup_is_bounded_and_attempts_both_clients(
    configured, fake_live, monkeypatch, capsys, failure
):
    import asyncio

    async def close():
        if failure == "error":
            raise RuntimeError("secret-close-error")
        await asyncio.sleep(0.05)

    fake_live[0].close.side_effect = close
    monkeypatch.setattr(configured, "CLOSE_TIMEOUT_SECONDS", 0.001)
    assert configured.main(["doctor", "--live"]) == 1
    fake_live[1].close.assert_awaited_once()
    assert "secret-close-error" not in capsys.readouterr().out


@pytest.mark.parametrize("codespaces,address", [("true", "0.0.0.0"), ("false", "127.0.0.1")])
def test_start_replaces_process_with_protected_streamlit(
    configured, monkeypatch, tmp_path, capsys, codespaces, address
):
    import os
    import sys

    executed = []
    monkeypatch.setenv("CODESPACES", codespaces)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(os, "execv", lambda executable, args: executed.append((executable, args)))
    assert configured.main(["start"]) == 0
    executable, args = executed[0]
    assert executable == sys.executable
    assert args[:4] == [sys.executable, "-m", "streamlit", "run"]
    assert Path(args[4]) == ROOT / "app/streamlit_app.py"
    assert f"--server.address={address}" in args
    assert "--server.port=8501" in args
    assert "--server.enableXsrfProtection=true" in args
    assert "--server.enableCORS=true" in args
    assert "--browser.gatherUsageStats=false" in args
    assert Path.cwd() == ROOT
    assert "test-secret-never-display" not in capsys.readouterr().out


def test_help_does_not_require_config(launcher, capsys):
    with pytest.raises(SystemExit) as result:
        launcher.main(["--help"])
    assert result.value.code == 0
    output = capsys.readouterr().out
    assert "doctor" in output and "start" in output


def test_start_does_not_launch_without_config(launcher, monkeypatch):
    import os

    monkeypatch.setattr(os, "execv", lambda *args: pytest.fail("started without configuration"))
    assert launcher.main(["start"]) == 1


def test_old_python_has_clear_explanation(configured, monkeypatch, capsys):
    monkeypatch.setattr(configured.sys, "version_info", (3, 10))
    assert configured.main(["doctor"]) == 1
    assert "Python 3.11" in capsys.readouterr().out


def test_dotenv_load_uses_repo_root_without_overriding_environment(configured, monkeypatch):
    import dotenv

    calls = []
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **kw: calls.append((a, kw)))
    assert configured.main(["doctor"]) == 0
    assert calls == [((ROOT / ".env",), {"override": False})]


def test_live_real_sdks_send_only_minimal_apim_requests(configured, monkeypatch):
    import json

    import httpx
    from azure.core.pipeline.transport import AsyncHttpResponse

    from hanbit_assistant import clients

    requests = []

    async def model_send(client, request, **kwargs):
        requests.append((request.method, str(request.url)))
        assert request.headers["Ocp-Apim-Subscription-Key"] == "test-secret-never-display"
        payload = json.loads(request.content)
        assert payload["store"] is False
        assert payload["max_output_tokens"] == 64
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "resp_offline_test",
                "object": "response",
                "created_at": 0,
                "model": "test-model",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "id": "msg_test",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": "READY", "annotations": []}],
                    }
                ],
            },
        )

    class IndexResponse(AsyncHttpResponse):
        def __init__(self, request):
            super().__init__(request, None)
            self.status_code = 200
            self.headers = {"content-type": "application/json"}
            self.content_type = "application/json"

        def body(self):
            return b'{"name":"student01","fields":[]}'

        async def load_body(self):
            pass

    async def index_send(request, **kwargs):
        requests.append((request.method, request.url))
        assert request.headers["Ocp-Apim-Subscription-Key"] == "test-secret-never-display"
        assert request.headers["api-key"] == "test-secret-never-display"
        return IndexResponse(request)

    original_factory = clients.create_index_client

    def index_factory(settings):
        client = original_factory(settings)
        client._client._client._pipeline._transport.send = index_send
        return client

    monkeypatch.setattr(httpx.AsyncClient, "send", model_send)
    monkeypatch.setattr(clients, "create_index_client", index_factory)
    assert configured.main(["doctor", "--live"]) == 0
    assert len(requests) == 2
    assert requests[0] == ("POST", "https://example.invalid/agent-rag/openai/v1/responses")
    assert requests[1][0] == "GET"
    assert requests[1][1].startswith("https://example.invalid/agent-rag/search/indexes")
    assert "student01" in requests[1][1]


@pytest.fixture
def configured(launcher, monkeypatch):
    values = {
        "WORKSHOP_API_KEY": "test-secret-never-display",
        "OPENAI_BASE_URL": "https://example.invalid/agent-rag/openai/v1",
        "AZURE_SEARCH_ENDPOINT": "https://example.invalid/agent-rag/search",
        "AZURE_SEARCH_INDEX": "student01",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return launcher


@pytest.mark.parametrize(
    "name,value",
    [
        ("OPENAI_BASE_URL", "http://secret-in-url.invalid"),
        ("AZURE_SEARCH_INDEX", "student99-secret"),
        ("WORKSHOP_API_KEY", "REPLACE_WITH_YOUR_PERSONAL_KEY"),
        ("OPENAI_BASE_URL", "https://YOUR-APIM.azure-api.net/agent-rag/openai/v1"),
    ],
)
def test_invalid_or_example_config_is_rejected_without_values(
    configured, monkeypatch, capsys, name, value
):
    monkeypatch.setenv(name, value)
    assert configured.main(["doctor"]) == 1
    output = capsys.readouterr().out
    assert "설정" in output
    assert value not in output
    assert "test-secret-never-display" not in output
