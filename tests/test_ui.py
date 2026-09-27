from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).parents[1] / "app" / "streamlit_app.py")


def test_app_explains_missing_configuration_without_exposing_keys(monkeypatch):
    for name in [
        "WORKSHOP_API_KEY",
        "OPENAI_BASE_URL",
        "AZURE_SEARCH_ENDPOINT",
        "AZURE_SEARCH_INDEX",
    ]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert "한빛" in app.title[0].value
    assert any(".env" in element.value for element in app.info)
    assert any("WORKSHOP_API_KEY" in element.value for element in app.code)


def test_app_initializes_an_isolated_session_and_reset(monkeypatch):
    monkeypatch.setenv("WORKSHOP_API_KEY", "ui-test-key-never-display")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://a.net/agent-rag/openai/v1")
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://a.net/agent-rag/search")
    monkeypatch.setenv("AZURE_SEARCH_INDEX", "student01")
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert len(app.chat_input) == 1
    runtime = app.session_state["runtime"]
    old = runtime.chat.session.session_id
    app.button(key="reset_chat").click().run()
    assert not app.exception
    assert app.session_state["runtime"].chat.session.session_id != old
    assert app.session_state["messages"] == []
    assert "ui-test-key-never-display" not in str(app.markdown)
    app.session_state["runtime"].close()


def test_app_chat_submission_runs_real_agent(monkeypatch):
    import httpx
    from openai import AsyncOpenAI

    import hanbit_assistant.agent as agent_module

    monkeypatch.setenv("WORKSHOP_API_KEY", "ui-test-key-never-display")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://a.net/agent-rag/openai/v1")
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://a.net/agent-rag/search")
    monkeypatch.setenv("AZURE_SEARCH_INDEX", "student01")

    def make_api(settings):
        def handler(request):
            return httpx.Response(
                200,
                json={
                    "id": "resp_ui",
                    "object": "response",
                    "created_at": 1,
                    "model": "gpt-5.6-terra",
                    "status": "completed",
                    "output": [
                        {
                            "id": "msg_ui",
                            "type": "message",
                            "status": "completed",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "한빛 출장 도우미입니다.",
                                    "annotations": [],
                                }
                            ],
                        }
                    ],
                },
            )

        return AsyncOpenAI(
            base_url=settings.openai_base_url,
            api_key=settings.workshop_api_key,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr(agent_module, "create_openai_client", make_api)
    app = AppTest.from_file(APP).run()
    app.chat_input[0].set_value("안녕하세요").run()
    assert not app.exception
    assert len(app.session_state["messages"]) == 2
    assert app.session_state["messages"][-1]["text"] == "한빛 출장 도우미입니다."
    assert any("도구 실행" in element.label for element in app.expander)
    app.session_state["runtime"].close()


def test_runtime_reuses_event_loop_and_closes_clients():
    import asyncio

    from hanbit_assistant.config import Settings
    from hanbit_assistant.ui import SessionRuntime

    settings = Settings(
        "https://a.net/agent-rag/openai/v1", "x", "https://a.net/agent-rag/search", "student01"
    )
    runtime = SessionRuntime(settings)

    async def loop_id():
        return id(asyncio.get_running_loop())

    assert runtime.run(loop_id()) == runtime.run(loop_id())
    runtime.close()
    runtime.close()  # teardown is idempotent
