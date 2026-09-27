"""학생용 실행 도우미. 기본 doctor는 네트워크를 사용하지 않습니다."""

import argparse
import asyncio
import importlib.metadata
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE_TIMEOUT_SECONDS = 30
CLOSE_TIMEOUT_SECONDS = 3
REQUIRED_ENV = (
    "WORKSHOP_API_KEY",
    "OPENAI_BASE_URL",
    "AZURE_SEARCH_ENDPOINT",
    "AZURE_SEARCH_INDEX",
)


async def live_check(settings):
    from hanbit_assistant.clients import create_index_client, create_openai_client

    model = create_openai_client(settings)
    index = None
    try:
        async with asyncio.timeout(LIVE_TIMEOUT_SECONDS):
            index = create_index_client(settings)
            response = await model.with_options(max_retries=0, timeout=15.0).responses.create(
                model=settings.model,
                input="Reply with exactly READY.",
                store=False,
                max_output_tokens=64,
                reasoning={"effort": "none"},
            )
            if response.output_text.strip() != "READY":
                raise ValueError("model did not return READY")
            print("모델: READY")
            await index.get_index(settings.search_index, retry_total=0)
            print("본인 Search 인덱스: 접근 가능 (내용·설정 출력 없음)")
    finally:
        async with asyncio.timeout(CLOSE_TIMEOUT_SECONDS):
            results = await asyncio.gather(
                *(client.close() for client in (model, index) if client is not None),
                return_exceptions=True,
            )
            if any(isinstance(result, BaseException) for result in results):
                raise RuntimeError("client cleanup failed")


def main(argv=None):
    parser = argparse.ArgumentParser(description="6시간 실습 환경 점검 및 앱 실행")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="네트워크 없이 환경 설정 점검")
    doctor.add_argument(
        "--live", action="store_true", help="실제 모델·본인 Search 읽기 점검 (소액 과금)"
    )
    commands.add_parser("start", help="Streamlit 앱 실행 (종료: Ctrl+C, 포트 공개 금지)")
    args = parser.parse_args(argv)
    codespaces = os.environ.get("CODESPACES", "").lower() == "true"
    print("실행 환경: " + ("Codespaces (Ports에서 비공개 여부 확인 필요)" if codespaces else "로컬"))
    if sys.version_info < (3, 11):  # noqa: UP036 - explain direct runs outside uv
        print("Python 3.11 이상이 필요합니다. uv sync --frozen으로 환경을 준비하세요.")
        return 1
    try:
        for package in (
            "hanbit-travel-assistant",
            "agent-framework-core",
            "agent-framework-openai",
            "azure-search-documents",
            "openai",
            "httpx",
            "aiohttp",
            "python-dotenv",
            "streamlit",
        ):
            importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        print("의존성이 누락되었습니다. uv sync --frozen을 실행하세요.")
        return 1
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name, "").strip()]
    if missing:
        print("필수 설정 누락: " + ", ".join(missing))
        print(".env.example을 .env로 복사하고 강사에게 받은 개인 설정을 입력하세요.")
        return 1
    try:
        from hanbit_assistant.config import Settings

        if any(
            marker in os.environ[name].upper()
            for name in REQUIRED_ENV
            for marker in ("YOUR-APIM", "REPLACE_WITH_")
        ):
            raise ValueError("example configuration")
        settings = Settings.from_env()
    except (ValueError, ImportError):
        print(
            "설정 오류: .env.example의 예시 대신 강사가 배정한 HTTPS 주소·개인 키·인덱스를 확인하세요."
        )
        return 1
    if args.command == "start":
        address = "0.0.0.0" if codespaces else "127.0.0.1"
        print(
            "앱 실행: "
            + ("Ports 탭 → 8501 열기, 비공개 유지" if codespaces else "http://127.0.0.1:8501")
        )
        print("종료하려면 이 터미널에서 Ctrl+C를 누르세요.", flush=True)
        os.chdir(ROOT)
        # Replace this process: no daemon, shell, or orphan child on terminal close.
        os.execv(
            sys.executable,
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(ROOT / "app/streamlit_app.py"),
                f"--server.address={address}",
                "--server.port=8501",
                "--server.headless=true",
                "--server.enableXsrfProtection=true",
                "--server.enableCORS=true",
                "--browser.gatherUsageStats=false",
            ],
        )
        return 0
    if args.live:
        # SDK debug logs and exception messages can contain keys, URLs or bodies.
        previous_logging = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            asyncio.run(live_check(settings))
        except TimeoutError:
            print("실시간 점검 실패: 시간 제한 초과. 네트워크·할당량을 확인하세요.")
            return 1
        except Exception:  # noqa: BLE001 - never expose SDK exception bodies or credentials
            print("실시간 점검 실패: 개인 키·모델 배포·본인 인덱스·네트워크를 확인하세요.")
            print(
                "인덱스가 없다면 강사 안내에 따라 인덱싱 노트북을 실행하세요. 자동 생성하지 않습니다."
            )
            return 1
        finally:
            logging.disable(previous_logging)
        return 0
    print("오프라인 점검 완료: 설정·의존성 확인. 실제 연결은 doctor --live로 점검하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
