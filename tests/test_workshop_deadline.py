from hanbit_assistant.config import Settings


def test_multi_tool_default_deadline_allows_transient_model_latency():
    settings = Settings(
        "https://test.net/openai/v1", "test", "https://test.net/search", "instructor"
    )
    assert settings.timeout_seconds == 120
