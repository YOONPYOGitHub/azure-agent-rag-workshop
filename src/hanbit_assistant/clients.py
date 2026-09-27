"""APIM 경로와 키를 보존하는 실제 SDK 클라이언트."""

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from openai import AsyncOpenAI

from .config import Settings


def create_openai_client(settings: Settings) -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.openai_base_url,
        api_key=settings.workshop_api_key,
        default_headers={"Ocp-Apim-Subscription-Key": settings.workshop_api_key},
        timeout=settings.timeout_seconds,
        max_retries=1,
    )


def create_search_client(settings: Settings) -> SearchClient:
    return SearchClient(
        endpoint=settings.search_endpoint,
        index_name=settings.search_index,
        credential=AzureKeyCredential(settings.workshop_api_key),
        headers={"Ocp-Apim-Subscription-Key": settings.workshop_api_key},
        connection_timeout=10,
        read_timeout=30,
        retry_total=1,
    )


def create_index_client(settings: Settings) -> SearchIndexClient:
    return SearchIndexClient(
        endpoint=settings.search_endpoint,
        credential=AzureKeyCredential(settings.workshop_api_key),
        headers={"Ocp-Apim-Subscription-Key": settings.workshop_api_key},
        connection_timeout=10,
        read_timeout=30,
        retry_total=1,
    )
