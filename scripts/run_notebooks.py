#!/usr/bin/env python3
"""노트북 오프라인 검사와 명시적으로 선택한 비공개 라이브 실행."""

import argparse
import ast
import os
import sys
from pathlib import Path

import nbformat

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = (
    "00_setup.ipynb",
    "01_llm_and_tools.ipynb",
    "02_agent_framework.ipynb",
    "03_indexing.ipynb",
    "04_rag_and_citations.ipynb",
    "05_conversational_agent.ipynb",
    "06_evaluation_safety.ipynb",
)


def validate_notebooks():
    """네트워크 없이 형식·독립 부트스트랩·출력 제거·Python 구문을 검사합니다."""
    paths = sorted((ROOT / "notebooks").glob("*.ipynb"))
    if tuple(p.name for p in paths) != EXPECTED:
        raise ValueError("00~06 노트북 7개가 정확히 있어야 합니다.")
    for path in paths:
        nb = nbformat.read(path, as_version=4)
        nbformat.validate(nb)
        code_cells = [cell for cell in nb.cells if cell.cell_type == "code"]
        if not code_cells:
            raise ValueError(f"{path.name}: 코드 셀이 없습니다.")
        first = code_cells[0].source
        for token in ("ROOT", "sys.path", "load_dotenv", "Settings.from_env"):
            if token not in first:
                raise ValueError(f"{path.name}: 독립 실행 설정 누락: {token}")
        markdown = "\n".join(c.source for c in nb.cells if c.cell_type == "markdown")
        for heading in ("학습 목표", "개념", "관찰", "연습", "예시 해설"):
            if heading not in markdown:
                raise ValueError(f"{path.name}: 교육 항목 누락: {heading}")
        has_await = False
        for i, cell in enumerate(code_cells):
            if cell.outputs or cell.execution_count is not None:
                raise ValueError(f"{path.name}: 공개 노트북에 실행 출력이 남았습니다.")
            compile(cell.source, f"{path.name}:code-{i}", "exec", ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
            tree = ast.parse(cell.source)
            has_await |= any(isinstance(n, ast.Await) for n in ast.walk(tree))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    for keyword in node.keywords:
                        if (
                            keyword.arg in {"max_output_tokens", "max_tokens"}
                            and isinstance(keyword.value, ast.Constant)
                            and (
                                not isinstance(keyword.value.value, int)
                                or not 1 <= keyword.value.value <= 1500
                            )
                        ):
                            raise ValueError(f"{path.name}: 출력 토큰 제한 위반")
                        if keyword.arg in {"previous_response_id", "conversation"}:
                            raise ValueError(f"{path.name}: 서버 저장 대화 참조 금지")
            if "asyncio.run(" in cell.source:
                raise ValueError(f"{path.name}: top-level await를 사용하세요.")
        if not has_await:
            raise ValueError(f"{path.name}: await 실행 예제가 없습니다.")
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="오프라인 형식 검사만 수행 (기본)")
    mode.add_argument("--execute", action="store_true", help="실제 API 사용 및 03 인덱스 쓰기 허용")
    parser.add_argument(
        "--notebook",
        action="append",
        choices=[f"{i:02d}" for i in range(7)],
        help="실행 번호, 반복 지정 가능; 생략하면 7개 순서대로 실행",
    )
    parser.add_argument("--timeout", type=int, default=300, help="셀당 제한 시간(초)")
    args = parser.parse_args()
    paths = validate_notebooks()
    print(f"검사 완료: {len(paths)}개, nbformat/AST/출력 제거/학습 구조 확인 (네트워크 없음)")
    if not args.execute:
        return 0
    if args.timeout < 1:
        parser.error("--timeout은 양수여야 합니다.")
    # 결과에는 대화·도구 데이터가 들어갈 수 있으므로 Git 제외된 경로만 허용합니다.
    import subprocess

    from nbclient import NotebookClient

    ignored = subprocess.run(
        ["git", "check-ignore", "-q", ".local/notebook-runs/probe"], cwd=ROOT, check=False
    )
    if ignored.returncode != 0:
        raise RuntimeError(".local/이 Git 제외 대상인지 확인하세요.")
    os.umask(0o077)
    out = ROOT / ".local" / "notebook-runs"
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    out.chmod(0o700)
    selected = [p for p in paths if not args.notebook or p.name[:2] in args.notebook]
    for path in selected:
        nb = nbformat.read(path, as_version=4)
        # 매번 새 NotebookClient/커널: 이전 노트북의 Python 변수를 재사용하지 않습니다.
        client = NotebookClient(
            nb,
            timeout=args.timeout,
            kernel_name="python3",
            allow_errors=False,
            resources={"metadata": {"path": str(ROOT)}},
        )
        target = out / path.name
        failed = False
        try:
            client.execute()
        except Exception:  # noqa: BLE001 — keep raw notebook/SDK errors private
            # SDK 예외/셀 출력은 stdout에 내보내지 않습니다. 실패 노트북도 비공개 보존합니다.
            failed = True
        finally:
            nbformat.write(nb, target)
            target.chmod(0o600)
        print(f"{path.name}: {'실패' if failed else '실행 완료'} → .local/notebook-runs/")
        if failed:
            print("비공개 출력에서 실패 셀을 확인하세요. 실패는 성공으로 대체하지 않습니다.")
            return 1
    print(f"라이브 실행 완료: {len(selected)}개. 공개 원본 출력은 변경하지 않았습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
