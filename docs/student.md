# 수강생 안내

## 준비물
- VS Code + Python/Jupyter 확장, Python 3.11, [uv](https://docs.astral.sh/uv/getting-started/installation/)
- 강사가 배정한 개인 환경 파일. 학생 Azure 로그인·리소스 생성 권한은 불필요합니다.
- `*.azure-api.net`, `api.open-meteo.com`, `api.frankfurter.dev`로 HTTPS 접속 가능

## 실행
1. README의 clone → `uv sync --frozen` → `code .`를 실행합니다.
2. 개인 파일의 이름을 **.env**로 바꿔 저장소 루트에 놓습니다. Windows에서도 `.env.txt`가 아닌지 확인합니다.
3. Notebook의 커널을 저장소 **.venv**로 선택합니다. 셀은 위에서 아래로 실행합니다.
4. 03의 인덱스 업로드가 끝나야 04~06과 챗봇이 동작합니다.
5. `uv run streamlit run app/streamlit_app.py` 후 터미널에 나온 로컬 주소를 엽니다.

```dotenv
OPENAI_BASE_URL=https://<강사-gateway>/agent-rag/openai/v1
WORKSHOP_API_KEY=<본인 전용 키>
AZURE_SEARCH_ENDPOINT=https://<강사-gateway>/agent-rag/search
AZURE_SEARCH_INDEX=student01
OPENAI_MODEL=gpt-5.6-terra
```

키와 인덱스는 한 쌍입니다. `student01`을 다른 이름으로 바꿔도 권한은 생기지 않습니다. 위 `<...>`는 실제 값이 아니므로 강사의 파일을 사용하세요.

## Dev Container / Codespaces

`.devcontainer/`를 열면 Python과 uv 환경을 구성합니다. `uv sync --frozen` 후 .venv 커널을 선택하세요. Codespaces의 포트 공개 범위는 **Private**을 유지합니다. Codespaces 사용료는 Azure 비용과 별도입니다. 저장소를 fork하거나 공유할 때 `.env`를 포함하지 마세요.

## 챗봇 확인 질문
- 도쿄 1인 1박 숙박 한도와 세금 포함 여부는?
- 그 금액을 KRW로 환산해줘. 참고 환율 기준일도 알려줘.
- 런던 현재 날씨는?
- 한빛테크 자녀 대학 등록금 지원 한도는? → 제공 문서에서 확인할 수 없다고 해야 함
- 호텔을 예약하고 결제해줘. → 실제 예약/결제 기능이 없다고 해야 함

## 오류 해결
| 현상 | 확인 |
|---|---|
| import 실패 | `uv sync --frozen`, .venv 커널 |
| 401 | 키 누락/만료/잘못된 API 경로 |
| 403 | 본인 키와 인덱스 조합, APIM 권한 |
| 404 / 인덱스 없음 | 03 업로드와 경로 확인 |
| 400 | 배포명/입력 제한/허용되지 않은 기능; 초기화 후 짧은 질문 |
| 429 | 요청 속도·공유 모델 할당량; 잠시 후 재실행 |
| 413 | 본문 크기 초과, 업로드 배치 줄이기 |
| 날씨/환율 오류 | 외부 API/회사 네트워크 상태, 실제 실패를 가짜 데이터로 대체하지 않기 |
| 긴 대화 실패 | 새 대화 / 초기화. 앱은 20턴과 시간/도구 제한이 있고 게이트웨이 입력 크기도 제한됨 |

문제를 공유할 때 **키·HTTP 헤더·환경 파일·실행 노트북 전체**를 단체 채팅에 보내지 마세요. 에러 코드와 단계 번호만 먼저 공유하세요.

## 주의
- 모든 정책은 교육용 허구입니다. 실제 비밀·개인정보를 입력하지 않습니다.
- 기본 자료는 수정하지 마세요. 내용 변경 시 옛 청크 삭제까지 관리하는 완전 동기화 파이프라인은 이 샘플 범위 밖입니다.
- Markdown page는 PDF 인쇄 쪽 번호가 아닙니다.
- 답변에 인용이 있어도 원문과 주장 일치를 직접 확인합니다.
