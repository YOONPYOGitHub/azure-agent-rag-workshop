# 강사 운영 가이드

## 1. 수업 전 확인

- 기존 Foundry 계정에 `gpt-5.6-terra` 배포가 준비되어 있어야 합니다.
- 기존 APIM의 system-assigned managed identity와 Foundry 계정 범위의 **Cognitive Services OpenAI User** 역할을 확인합니다. 스크립트는 공유 Foundry 역할을 임의로 확대하지 않습니다.
- 강사 Azure CLI 로그인(`az login`)과 대상 구독의 리소스 생성·좁은 범위 역할 할당·APIM 관리 권한이 필요합니다. 학생은 Azure 계정이 필요 없습니다.
- 조직의 공용 HTTPS 엔드포인트, 지역, GlobalStandard 모델 사용 정책을 확인합니다. 기본 자료는 공개 가능한 허구 문서뿐입니다.
- `uv sync --frozen`, 오프라인 테스트, 비용/수업 종료 후 삭제 계획을 확인합니다.

## 2. 구성

| 대상 | 구성 |
|---|---|
| 공유 Foundry | 기존 LLM 배포 유지, `text-embedding-3-small` 추가 배포 |
| 임베딩 | 1536차원, 이 계정에서 지원 확인된 GlobalStandard, capacity 30 |
| 전용 RG | `rg-agent-rag-workshop`, 한국 중부 |
| Search | Basic, replica 1 / partition 1, 로컬 키 인증 비활성 |
| 기존 APIM | 새 전용 `agent-rag-workshop` API, 경로 `/agent-rag`만 추가 |
| 개인 접근 | student01~student10 + instructor, API-scoped subscription 11개 |
| 실행 환경 | 학생 PC/Dev Container에서 Notebook와 Streamlit 실행 |

기본 단일 replica 구성은 교육용이며 고가용성 SLA 목적이 아닙니다. 별도 Foundry 프로젝트나 호스팅 에이전트 리소스, App Service, Storage 리소스는 만들지 않습니다.

## 3. 읽기 전용 사전 점검 → 명시적 생성

다음은 Bash 예시입니다. `<...>`에 실제 환경 값을 넣습니다. 공유 리소스 정보와 구독 ID는 배포 담당자가 관리하며 public repo에 키를 넣지 않습니다.

```bash
az login
uv run python infra/provision.py \
  --subscription '<구독 ID>' \
  --foundry-rg '<기존 Foundry RG>' --foundry-name '<기존 Foundry 계정>' \
  --apim-rg '<기존 APIM RG>' --apim-name '<기존 APIM 이름>' \
  --embedding-sku GlobalStandard --dry-run
```

사전 점검에 성공하면 동일 명령의 `--dry-run`을 **`--apply`**로 바꿉니다. 새 서비스의 provisioning에는 시간이 걸릴 수 있습니다. 실패 시 새 리소스를 무작정 더 만들지 말고 `.local/provision-manifest.json`을 유지한 채 원인을 확인하고 같은 명령을 재실행합니다.

스크립트는 변경 전 manifest에 대상을 기록합니다. **manifest는 재실행·안전한 삭제에 필요하므로 비공개 백업**하세요. 같은 이름의 타 작업 리소스를 자동 인수하거나 기존 키를 임의 회전하지 않습니다. 기존 공유 API 정책은 변경하지 않습니다.

## 4. 개인 키 배포

생성/읽기 검증 후 `.local/attendees/`에 다음 파일이 생깁니다.

- `student01.env` … `student10.env`: 학생에게 **각자 본인 파일 하나만** 개인 채널로 전달
- `instructor.env`: 강사 전용, 학생에게 배포하지 않음

학생은 받은 파일을 저장소 루트의 `.env`로 저장합니다. 이 파일을 공개 채팅·GitHub·전체 수강생에게 공유하지 마세요. 강사용 파일 권한은 로컬에서 0600으로 설정합니다.

## 5. 수업 전 실제 검증

```bash
# 강사 파일을 root .env로 복사 — 비공개
cp .local/attendees/instructor.env .env
# Windows PowerShell: Copy-Item .local/attendees/instructor.env .env

uv run python scripts/run_notebooks.py --check
uv run python scripts/run_notebooks.py --execute
uv run python scripts/live_security_check.py
uv run streamlit run app/streamlit_app.py
```

- 노트북은 별도 커널에서 순서대로 실행합니다. 03이 실제 인덱스를 생성/업로드합니다.
- 10명 동시 요청 검사는 학생별 개인 키를 사용합니다. 이는 **작은 실측 smoke test**이지 수업 내내 공유 모델 용량을 보장하는 부하 인증은 아닙니다.
- 다른 인덱스·서비스 관리·다른 API·이전 서버 응답 접근은 거부되어야 합니다.
- 성공 코드만으로 완료라고 판단하지 말고 문서 개수, 검색 결과, 출처, 실제 도구 호출까지 확인합니다.
- `.local/notebook-runs/`와 `.local/security-check.json`은 비공개입니다. public 원본은 출력 없는 상태를 유지합니다.

## 6. 비용과 할당량

한국 중부 Azure Retail Prices API 확인값(2026-09-27): Search Basic **US$0.101/시간**. 4시간 US$0.404, 하루 US$2.424, 7일 US$16.968, 730시간 가정 US$73.73입니다. Search 1 unit 기준이며 세금/계약 할인·모델/임베딩·APIM은 제외입니다.

**유휴 상태여도 Search 비용이 발생하며 삭제해야 멈춥니다.** 무료 정지 버튼이나 예산 자동 차단을 가정하지 마세요. 과금 알림/조직 budget은 별도로 설정하며 budget은 일반적으로 경고이지 자동 정지가 아닙니다. 이 저장소는 구독 전체의 예산 정책을 수정하지 않습니다.

개인별 APIM 요청 제한과 모델 입력/출력 제한이 있습니다. 기존 공유 모델의 다른 트래픽도 있으므로 수업 전 실제 10명 테스트를 다시 수행하세요. 429가 발생하면 반복 요청을 멈추고 Retry-After/할당량을 확인합니다.

## 7. 수업 후 폐기

먼저 삭제 계획을 확인합니다. **다음 명령은 기본적으로 dry-run**입니다.

```bash
uv run python infra/teardown.py --confirm rg-agent-rag-workshop --dry-run
# 대상 확인 후에만 실행
uv run python infra/teardown.py --confirm rg-agent-rag-workshop --apply
```

manifest 소유의 개인 subscriptions, 전용 API, 추가 임베딩 배포, Search 역할 할당, 전용 RG만 삭제합니다. 공유 Foundry/APIM 부모는 삭제하지 않습니다. 전용 RG에 알 수 없는 다른 리소스가 있으면 group 삭제를 거부합니다. 로컬 env 파일은 자동으로 지워지지 않지만 원격 subscription 삭제 후 사용할 수 없게 됩니다.

> 실제 삭제는 수업이 끝난 뒤 수행하세요. 저장소 제작 시에는 학생 실습을 위해 리소스를 남겨둡니다.
