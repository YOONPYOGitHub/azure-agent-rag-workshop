import pytest


def test_apim_settings_and_client_use_the_same_key(monkeypatch):
    from hanbit_assistant.clients import create_openai_client, create_search_client
    from hanbit_assistant.config import Settings

    values = {
        "OPENAI_BASE_URL": "https://workshop.azure-api.net/agent-rag/openai/v1",
        "WORKSHOP_API_KEY": "test-key-not-a-secret",
        "AZURE_SEARCH_ENDPOINT": "https://workshop.azure-api.net/agent-rag/search",
        "AZURE_SEARCH_INDEX": "student01",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    settings = Settings.from_env()
    assert settings.model == "gpt-5.6-terra"
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.embedding_dimensions == 1536
    assert values["WORKSHOP_API_KEY"] not in repr(settings)
    client = create_openai_client(settings)
    assert client.api_key == values["WORKSHOP_API_KEY"]
    assert client.default_headers["Ocp-Apim-Subscription-Key"] == client.api_key
    search = create_search_client(settings)
    assert search._credential.key == client.api_key
    assert (
        search._client._config.headers_policy.headers["Ocp-Apim-Subscription-Key"] == client.api_key
    )


def test_settings_reject_missing_credentials(monkeypatch):
    from hanbit_assistant.config import Settings

    monkeypatch.delenv("WORKSHOP_API_KEY", raising=False)
    with pytest.raises(ValueError, match="WORKSHOP_API_KEY"):
        Settings.from_env()
