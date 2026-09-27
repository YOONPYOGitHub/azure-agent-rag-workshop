# 강사 전용 Azure 구성

전체 절차는 [강사 가이드](../docs/instructor.md), 접근 경계는 [보안 문서](../docs/security.md)를 따르세요.

- `provision.py`: 읽기 전용 사전 점검이 기본입니다. `--apply`를 명시해야 리소스/개인 키를 생성합니다.
- `security.py`, `apim-policy.xml.tpl`: 개인 키별 인덱스와 허용 경로, 모델/본문 크기/도구 제한을 정의합니다.
- `teardown.py`: manifest에 기록된 워크숍 리소스만 삭제합니다. 기본은 dry-run입니다.
- `tests/`: Python 정책 계약/SDK 실제 요청 형식/재실행/삭제 경계 테스트입니다. C# APIM 런타임을 대체하는 검사는 아닙니다.
- [DISCOVERY.md](DISCOVERY.md): 실제 배포 중 확인한 현재 SDK와 Azure 응답 형식의 호환성 메모입니다.

```bash
uv run python infra/provision.py \
  --subscription '<구독 ID>' \
  --foundry-rg '<기존 RG>' --foundry-name '<기존 Foundry>' \
  --apim-rg '<기존 RG>' --apim-name '<기존 APIM>' \
  --embedding-sku GlobalStandard --dry-run
# 위 사전 점검 성공 후 --dry-run을 --apply로 변경

uv run pytest tests infra/tests -q
uv run python scripts/live_security_check.py

uv run python infra/teardown.py --confirm rg-agent-rag-workshop --dry-run
```

개인 키는 `.local/attendees/`에 저장하며 `.local/provision-manifest.json`은 비공개로 백업합니다. manifest를 잃으면 기존 리소스를 자동 인수하지 않습니다. 이미 생성된 동일 리소스는 읽기 검증으로 재사용하며 키를 자동 회전하지 않습니다.

본문 제한은 모델 256KiB / Search 2MiB입니다. API-scoped 키에는 분당 60회 rate-limit을 사용하고 **일별 quota는 설치하지 않습니다**. `quota`는 product scope 전용입니다. 요청 수·토큰 제한을 금액 예산의 강제 차단으로 설명하지 마세요.

실습 후 리소스를 삭제하지 않으면 Search 요금이 계속 발생합니다. 공유 Foundry/APIM 부모와 기존 API는 삭제 대상이 아닙니다.
