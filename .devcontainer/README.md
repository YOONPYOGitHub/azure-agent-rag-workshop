# Codespaces 실행 환경

- 컨테이너 생성은 `uv sync --frozen`만 실행합니다. 앱·리소스·인덱스는 자동 생성하지 않습니다.
- `.env.example`을 `.env`로 복사해 강사가 배정한 설정을 입력하거나 Codespaces secrets를 사용하세요.
- **Terminal → Run Task → Workshop: doctor**로 오프라인 점검 후 **Workshop: start**를 실행하세요.
- 실제 연결 확인은 터미널에서 `uv run python scripts/workshop.py doctor --live`를 명시적으로 실행합니다.
  모델에 `READY`만 요청하고 본인 Search 인덱스 정의만 읽습니다. 저장·임베딩·업로드·프로비저닝은 하지 않습니다.
  요청 전체 30초, 클라이언트 종료 추가 3초 제한이며 소액 모델 사용료가 발생할 수 있습니다.
- 앱은 Codespaces에서 `0.0.0.0:8501`, 로컬에서 `127.0.0.1:8501`에 바인딩합니다.
  CORS/XSRF 보호를 끄지 않습니다. 앱 종료는 실행 터미널에서 **Ctrl+C**입니다.

## 비공개 포트

8501만 전달하고 다른 포트의 자동 전달은 무시합니다. 로컬 전달은 localhost에 제한합니다.
Codespaces의 기본 **Private** 포트 전달을 사용하며, **Ports → 8501 → Port Visibility → Private**를 확인하세요.
이전에 공개로 바꿨다면 먼저 Private로 되돌려야 합니다. 앱에는 별도 사용자 로그인이 없으므로 공개하지 마세요.

`devcontainer.json`의 표준 포트 속성에는 강제 `visibility` 설정이 없습니다.
지원하지 않는 설정이나 `gh` 명령으로 공개 범위를 바꾸지 않습니다. 조직 차원의 강제 제한은 관리자의 Codespaces 정책이 필요합니다.

참고: [GitHub 포트 전달](https://docs.github.com/en/codespaces/developing-in-a-codespace/forwarding-ports-in-your-codespace),
[Dev Container 포트 속성](https://containers.dev/implementors/json_reference/#port-attributes).
