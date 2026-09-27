from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from hanbit_assistant.config import Settings


@pytest.fixture
def settings():
    return Settings(
        "https://a.net/agent-rag/openai/v1",
        "test-key",
        "https://a.net/agent-rag/search",
        "student01",
    )


def search_dependencies(rows=None):
    async def results():
        for row in rows or []:
            yield row

    search = SimpleNamespace(
        search=AsyncMock(side_effect=lambda **kw: results()), close=AsyncMock()
    )
    openai = SimpleNamespace(
        embeddings=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(
                    data=[SimpleNamespace(index=0, embedding=[0.1] * 1536)]
                )
            )
        ),
        close=AsyncMock(),
    )
    index = SimpleNamespace(close=AsyncMock())
    return openai, search, index


@pytest.mark.parametrize(
    "mode,uses_text,uses_vector",
    [("keyword", True, False), ("vector", False, True), ("hybrid", True, True)],
)
async def test_search_modes_return_citable_results_and_escape_filters(
    settings, mode, uses_text, uses_vector
):
    from hanbit_assistant.search import PolicySearch

    row = {
        "id": "abc123",
        "title": "출장",
        "content": "규정 내용",
        "source": "data/policies/team's.md",
        "section": "승인",
        "page": 1,
        "@search.score": 0.5,
    }
    openai, search, index = search_dependencies([row])
    service = PolicySearch(settings, openai_client=openai, search_client=search, index_client=index)
    result = await service.search("출장 승인", mode=mode, source="data/policies/team's.md", top=3)
    args = search.search.call_args.kwargs
    assert args["search_text"] == ("출장 승인" if uses_text else None)
    assert bool(args.get("vector_queries")) == uses_vector
    assert args["filter"] == "source eq 'data/policies/team''s.md'"
    assert args["top"] == 3
    assert result[0]["citation"] == "[abc123]"
    assert "content_vector" not in args["select"]
    assert openai.embeddings.create.await_count == int(uses_vector)


async def test_search_validates_mode_top_query_before_network(settings):
    from hanbit_assistant.search import PolicySearch

    openai, search, index = search_dependencies()
    service = PolicySearch(settings, openai_client=openai, search_client=search, index_client=index)
    for kwargs in [{"mode": "bogus"}, {"top": 0}, {"top": 100}, {"source": "https://evil"}]:
        with pytest.raises(ValueError):
            await service.search("q", **kwargs)
    with pytest.raises(ValueError):
        await service.search(" ")
    search.search.assert_not_called()


async def test_index_upload_checks_individual_failures(settings):
    from hanbit_assistant.search import PolicySearch

    openai, search, index = search_dependencies()
    index.create_or_update_index = AsyncMock(return_value="created")
    search.upload_documents = AsyncMock(return_value=[SimpleNamespace(succeeded=True)])
    search.get_document = AsyncMock(return_value={"id": "abc", "content": "내용"})
    service = PolicySearch(settings, openai_client=openai, search_client=search, index_client=index)
    assert await service.create_index() == "created"
    chunks = [
        {
            "id": "abc",
            "title": "제목",
            "content": "내용",
            "source": "data/policies/a.md",
            "section": "절",
            "page": 1,
        }
    ]
    assert await service.upload_chunks(chunks) == 1
    assert "content_vector" not in chunks[0]
    assert len(search.upload_documents.call_args.kwargs["documents"][0]["content_vector"]) == 1536
    search.upload_documents.return_value = [SimpleNamespace(succeeded=False)]
    with pytest.raises(RuntimeError, match="업로드"):
        await service.upload_chunks(chunks)


async def test_compare_runs_all_three_modes(settings):
    from hanbit_assistant.search import PolicySearch

    openai, search, index = search_dependencies()
    service = PolicySearch(settings, openai_client=openai, search_client=search, index_client=index)
    assert list(await service.compare("출장")) == ["keyword", "vector", "hybrid"]
    assert search.search.await_count == 3
    await service.close()
    # Caller-injected clients remain caller-owned.
    openai.close.assert_not_called()


def test_index_supports_korean_bm25_vector_and_opt_in_semantic():
    from hanbit_assistant.search import build_index

    index = build_index("student01")
    fields = {f.name: f for f in index.fields}
    assert fields["id"].key
    assert fields["content"].analyzer_name == "ko.microsoft"
    assert fields["content_vector"].vector_search_dimensions == 1536
    assert fields["source"].filterable
    assert fields["page"].type == "Edm.Int32"
    assert index.semantic_search is None
    semantic = build_index("student01", semantic=True)
    assert semantic.semantic_search.configurations[0].name == "policy-semantic"
    assert "content_vector" in {f["name"] for f in index.serialize()["fields"]}


async def test_embeddings_request_fixed_dimensions_and_preserve_order():
    from hanbit_assistant.search import embed_texts

    api = SimpleNamespace(
        embeddings=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(
                    data=[
                        SimpleNamespace(index=1, embedding=[0.2] * 1536),
                        SimpleNamespace(index=0, embedding=[0.1] * 1536),
                    ]
                )
            )
        )
    )
    result = await embed_texts(api, ["first", "second"])
    assert [r[0] for r in result] == [0.1, 0.2]
    assert api.embeddings.create.call_args.kwargs == {
        "input": ["first", "second"],
        "model": "text-embedding-3-small",
        "dimensions": 1536,
    }


async def test_embeddings_reject_dimension_mismatch():
    from hanbit_assistant.search import embed_texts

    api = SimpleNamespace(
        embeddings=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[0.1])])
            )
        )
    )
    with pytest.raises(ValueError, match="1536"):
        await embed_texts(api, ["text"])
