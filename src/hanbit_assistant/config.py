"""학생은 APIM 개인 구독 키 하나만 사용합니다."""

import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    openai_base_url: str
    workshop_api_key: str = field(repr=False)
    search_endpoint: str
    search_index: str
    model: str = "gpt-5.6-terra"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    semantic: bool = False
    timeout_seconds: float = 120.0
    max_tool_calls: int = 6

    def __post_init__(self):
        for name, value in (
            ("OPENAI_BASE_URL", self.openai_base_url),
            ("AZURE_SEARCH_ENDPOINT", self.search_endpoint),
        ):
            url = urlsplit(value)
            if url.scheme != "https" or not url.hostname or url.username or url.query:
                raise ValueError(f"{name}: HTTPS 서비스 주소가 필요합니다.")
        if not self.workshop_api_key.strip():
            raise ValueError("WORKSHOP_API_KEY를 설정하세요.")
        if not re.fullmatch(r"(?:student(?:0[1-9]|10)|instructor)", self.search_index):
            raise ValueError("AZURE_SEARCH_INDEX: 배정받은 student01..student10 또는 instructor")
        if self.embedding_dimensions != 1536:
            raise ValueError("이 실습 인덱스의 벡터 차원은 1536입니다.")
        if self.timeout_seconds <= 0 or not 1 <= self.max_tool_calls <= 12:
            raise ValueError("시간 제한과 도구 호출 제한을 확인하세요.")

    @classmethod
    def from_env(cls):
        required = [
            "WORKSHOP_API_KEY",
            "OPENAI_BASE_URL",
            "AZURE_SEARCH_ENDPOINT",
            "AZURE_SEARCH_INDEX",
        ]
        for name in required:
            if not os.environ.get(name, "").strip():
                raise ValueError(f"{name}를 .env에 설정하세요.")
        return cls(
            openai_base_url=os.environ["OPENAI_BASE_URL"].rstrip("/"),
            workshop_api_key=os.environ["WORKSHOP_API_KEY"],
            search_endpoint=os.environ["AZURE_SEARCH_ENDPOINT"].rstrip("/"),
            search_index=os.environ["AZURE_SEARCH_INDEX"],
            model=os.getenv("OPENAI_MODEL", "gpt-5.6-terra"),
            semantic=os.getenv("AZURE_SEARCH_SEMANTIC", "false").lower() == "true",
        )
