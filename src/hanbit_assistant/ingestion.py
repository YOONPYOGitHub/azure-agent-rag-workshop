"""Markdown → 제목/절/쪽 메타데이터가 있는 재현 가능한 작은 청크.

Markdown은 실제 인쇄 쪽이 없으므로 기본 page=1입니다.
명시적 <!-- page: 2 --> 마커가 있을 때만 페이지가 바뀝니다.
"""

import hashlib
import re
from pathlib import Path, PurePosixPath


def validate_source(source: str) -> str:
    path = PurePosixPath(source)
    if (
        not source.startswith("data/policies/")
        or ".." in path.parts
        or "\\" in source
        or ":" in source
        or path.suffix != ".md"
        or any(ord(c) < 32 for c in source)
    ):
        raise ValueError("출처는 data/policies/ 아래의 안전한 Markdown 상대 경로여야 합니다.")
    return source


def chunk_markdown(text: str, source: str, max_chars: int = 1000, overlap: int = 150) -> list[dict]:
    validate_source(source)
    if max_chars < 1 or not 0 <= overlap < max_chars:
        raise ValueError("0 <= overlap < max_chars 조건이 필요합니다.")
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else PurePosixPath(source).stem
    section, page, lines, chunks = title, 1, [], []

    def flush():
        content = "\n".join(lines).strip()
        start = 0
        while start < len(content):
            end = min(start + max_chars, len(content))
            # 가능하면 문단/줄/단어 경계에서 자릅니다. 끝없이 짧아지지 않도록 제한합니다.
            if end < len(content):
                boundary = max(content.rfind("\n", start, end), content.rfind(" ", start, end))
                if boundary > start + max(max_chars // 2, overlap):
                    end = boundary
            piece = content[start:end].strip()
            if piece:
                identity = f"{source}|{page}|{section}|{len(chunks)}|{piece}"
                chunks.append(
                    {
                        "id": hashlib.sha256(identity.encode()).hexdigest(),
                        "title": title,
                        "content": piece,
                        "source": source,
                        "section": section,
                        "page": page,
                    }
                )
            if end == len(content):
                break
            start = end - overlap
        lines.clear()

    for line in text.splitlines():
        marker = re.fullmatch(r"\s*<!--\s*page:\s*(\d+)\s*-->\s*", line, re.IGNORECASE)
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if marker:
            flush()
            page = max(1, int(marker.group(1)))
        elif heading:
            flush()
            section = heading.group(2).strip()
        else:
            lines.append(line)
    flush()
    return chunks


def load_policy_chunks(directory: str | Path = "data/policies") -> list[dict]:
    directory = Path(directory)
    paths = sorted(directory.rglob("*.md"))
    if not paths:
        raise ValueError("정책 Markdown 파일을 찾지 못했습니다. 저장소 루트에서 실행하세요.")
    chunks = []
    for path in paths:
        if not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError("정책 폴더 밖을 가리키는 링크는 읽을 수 없습니다.")
        source = "data/policies/" + path.relative_to(directory).as_posix()
        chunks.extend(chunk_markdown(path.read_text(encoding="utf-8"), source))
    return chunks
