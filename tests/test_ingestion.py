import pytest


def test_markdown_chunks_keep_section_page_source_and_deterministic_ids():
    from hanbit_assistant.ingestion import chunk_markdown

    text = (
        "# 출장 규정\n\n## 승인\n팀장 승인 필요.\n<!-- page: 2 -->\n## 숙박\n"
        + "숙박 상한액 확인. " * 50
    )
    chunks = chunk_markdown(text, "data/policies/travel.md", max_chars=150, overlap=20)
    assert len(chunks) > 2
    assert chunks == chunk_markdown(text, "data/policies/travel.md", max_chars=150, overlap=20)
    assert len({c["id"] for c in chunks}) == len(chunks)
    assert all(len(c["content"]) <= 150 for c in chunks)
    assert all(c["source"] == "data/policies/travel.md" for c in chunks)
    assert all(c["title"] == "출장 규정" for c in chunks)
    assert chunks[0]["section"] == "승인" and chunks[0]["page"] == 1
    assert chunks[-1]["section"] == "숙박" and chunks[-1]["page"] == 2
    assert all("page:" not in c["content"] for c in chunks)


@pytest.mark.parametrize(
    "source",
    [
        "../secret.md",
        "/etc/passwd",
        "https://evil.test/a",
        "data/../secret.md",
        "data\\policies\\a.md",
    ],
)
def test_chunking_rejects_unsafe_source(source):
    from hanbit_assistant.ingestion import chunk_markdown

    with pytest.raises(ValueError):
        chunk_markdown("content", source)


def test_load_policy_chunks_uses_sorted_repo_relative_sources(tmp_path):
    from hanbit_assistant.ingestion import load_policy_chunks

    policies = tmp_path / "data" / "policies"
    policies.mkdir(parents=True)
    (policies / "b.md").write_text("# B\n내용 B", encoding="utf-8")
    (policies / "a.md").write_text("# A\n내용 A", encoding="utf-8")
    chunks = load_policy_chunks(policies)
    assert [c["source"] for c in chunks] == ["data/policies/a.md", "data/policies/b.md"]


def test_empty_and_invalid_chunk_parameters():
    from hanbit_assistant.ingestion import chunk_markdown

    assert chunk_markdown("  ", "data/policies/a.md") == []
    with pytest.raises(ValueError):
        chunk_markdown("text", "data/policies/a.md", max_chars=20, overlap=20)
