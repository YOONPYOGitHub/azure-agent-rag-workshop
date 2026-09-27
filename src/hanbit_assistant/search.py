"""Azure AI Search: BM25 / 벡터 / 하이브리드 비교용 공통 코드."""

import asyncio

from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from azure.search.documents.models import VectorizedQuery

from .clients import create_index_client, create_openai_client, create_search_client
from .config import Settings
from .ingestion import validate_source

DIMENSIONS = 1536
RESULT_FIELDS = ["id", "title", "content", "source", "section", "page"]


class PolicySearch:
    """인덱스는 설정에서만 선택합니다. 도구 입력으로 인덱스를 바꿀 수 없습니다.

    APIM이 키별 인덱스 접근을 서버에서 강제해야 합니다. 이 검증은 보안 경계가 아닙니다.
    주입한 SDK 클라이언트는 호출자가 닫고, 직접 만든 클라이언트만 close()가 닫습니다.
    """

    def __init__(
        self, settings: Settings, openai_client=None, search_client=None, index_client=None
    ):
        self.settings = settings
        self.openai = openai_client or create_openai_client(settings)
        self.client = search_client or create_search_client(settings)
        self.index_client = index_client or create_index_client(settings)
        self._owned = [
            client
            for supplied, client in (
                (openai_client, self.openai),
                (search_client, self.client),
                (index_client, self.index_client),
            )
            if supplied is None
        ]

    async def create_index(self):
        """명시적 쓰기 작업: 본인 인덱스만 생성/갱신. 앱 시작 시 자동 호출하지 않습니다."""
        async with asyncio.timeout(self.settings.timeout_seconds):
            return await self.index_client.create_or_update_index(
                build_index(self.settings.search_index, self.settings.semantic)
            )

    async def upload_chunks(self, chunks: list[dict]) -> int:
        """동일 청크 ID로 재실행하면 덮어씁니다. 삭제된 원문의 옛 청크는 자동 삭제하지 않습니다."""
        for chunk in chunks:
            validate_source(chunk["source"])
        uploaded = 0
        for start in range(0, len(chunks), 16):
            batch = chunks[start : start + 16]
            async with asyncio.timeout(self.settings.timeout_seconds):
                vectors = await embed_texts(
                    self.openai, [c["content"] for c in batch], self.settings.embedding_model
                )
                documents = [{**c, "content_vector": v} for c, v in zip(batch, vectors)]
                results = await self.client.upload_documents(documents=documents)
            if len(results) != len(batch) or any(not r.succeeded for r in results):
                raise RuntimeError(
                    "일부 청크 업로드에 실패했습니다. 키/인덱스/할당량을 확인하고 재실행하세요."
                )
            uploaded += len(results)
        return uploaded

    async def search(
        self, query: str, mode: str = "hybrid", top: int = 5, source: str | None = None
    ) -> list[dict]:
        if mode not in {"keyword", "vector", "hybrid"}:
            raise ValueError("mode: keyword, vector, hybrid 중 하나를 선택하세요.")
        if not query.strip() or len(query) > 2000 or not 1 <= top <= 10:
            raise ValueError("검색어는 1~2000자, top은 1~10이어야 합니다.")
        source_filter = None
        if source is not None:
            validate_source(source)
            source_filter = "source eq '" + source.replace("'", "''") + "'"
        kwargs = {
            "search_text": query if mode != "vector" else None,
            "top": top,
            "select": RESULT_FIELDS,
            "filter": source_filter,
        }
        async with asyncio.timeout(self.settings.timeout_seconds):
            if mode != "keyword":
                vector = (await embed_texts(self.openai, [query], self.settings.embedding_model))[0]
                kwargs["vector_queries"] = [
                    VectorizedQuery(vector=vector, fields="content_vector", k_nearest_neighbors=50)
                ]
            if self.settings.semantic and mode != "vector":
                kwargs.update(query_type="semantic", semantic_configuration_name="policy-semantic")
            results = await self.client.search(**kwargs)
            rows = []
            async for result in results:
                validate_source(result["source"])
                row = {name: result.get(name) for name in RESULT_FIELDS}
                row.update(
                    citation=f"[{row['id']}]",
                    score=result.get("@search.score"),
                    reranker_score=result.get("@search.reranker_score"),
                )
                rows.append(row)
            return rows

    async def compare(self, query: str, top: int = 3) -> dict[str, list[dict]]:
        """점수 척도가 서로 다르므로 점수 크기 대신 순위/관련성을 비교하세요."""
        return {
            mode: await self.search(query, mode=mode, top=top)
            for mode in ("keyword", "vector", "hybrid")
        }

    async def close(self):
        for client in self._owned:
            await client.close()
        self._owned.clear()


def build_index(index_name: str, semantic: bool = False) -> SearchIndex:
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(
            name="title", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"
        ),
        SearchableField(
            name="content", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"
        ),
        SimpleField(name="source", type=SearchFieldDataType.String, filterable=True),
        SearchableField(
            name="section", type=SearchFieldDataType.String, analyzer_name="ko.microsoft"
        ),
        SimpleField(name="page", type=SearchFieldDataType.Int32, filterable=True),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=DIMENSIONS,
            vector_search_profile_name="policy-vector",
        ),
    ]
    semantic_search = None
    if semantic:
        semantic_search = SemanticSearch(
            configurations=[
                SemanticConfiguration(
                    name="policy-semantic",
                    prioritized_fields=SemanticPrioritizedFields(
                        title_field=SemanticField(field_name="title"),
                        content_fields=[SemanticField(field_name="content")],
                    ),
                )
            ]
        )
    return SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="policy-hnsw")],
            profiles=[
                VectorSearchProfile(
                    name="policy-vector", algorithm_configuration_name="policy-hnsw"
                )
            ],
        ),
        semantic_search=semantic_search,
    )


async def embed_texts(
    client, texts: list[str], model: str = "text-embedding-3-small"
) -> list[list[float]]:
    """작은 배치로 임베딩. 응답 순서를 index로 복원하고 차원을 검증합니다."""
    vectors = []
    for start in range(0, len(texts), 16):
        batch = texts[start : start + 16]
        response = await client.embeddings.create(input=batch, model=model, dimensions=DIMENSIONS)
        data = sorted(response.data, key=lambda item: item.index)
        if [item.index for item in data] != list(range(len(batch))):
            raise ValueError("임베딩 응답 개수가 요청과 다릅니다.")
        for item in data:
            if len(item.embedding) != DIMENSIONS:
                raise ValueError("임베딩 벡터는 1536차원이어야 합니다.")
            vectors.append(item.embedding)
    return vectors
