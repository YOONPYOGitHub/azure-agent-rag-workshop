# 배포 호환성 메모

- 실제 검증한 조합: Agent Framework core 1.19.0 / openai provider 1.14.4, Azure Search SDK 11.6.0. 잠금 파일로 설치합니다.
- 현재 Responses 클라이언트는 `OpenAIChatClient`입니다. 로컬 세션 재전달에 encrypted reasoning, function_call id, assistant output_text의 logprobs 메타데이터가 포함될 수 있습니다.
- Azure Search SDK는 OData `indexes('name')` 및 `docs/search.index`, `docs/search.post.search` 경로를 사용합니다. APIM은 표준 REST와 이 별칭을 동일한 개인 인덱스 경계로 검사합니다.
- APIM backend 선택 후 URL이 달라질 수 있으므로 Search rewrite는 `OriginalUrl.Path`를 기준으로 합니다.
- XML로 이스케이프한 정책은 `format=xml`로 저장하고 같은 형식으로 읽어 트리를 비교합니다. rawxml 응답은 C# generics 때문에 XML parser로 직접 읽을 수 없을 수 있습니다.
- `quota`는 product scope 전용이므로 API-scoped 개인 키 구성에는 넣지 않습니다. API의 subscription rate-limit만 적용하며 일별/금액 예산 상한은 없습니다.
- Search `disableLocalAuth=true`일 때 authOptions를 함께 설정하지 않습니다. readback의 지역 표시 이름(예: Korea Central)과 ARM 지역 식별자를 비교할 때만 지역 표기를 맞춥니다. 모델·인덱스 식별자는 그대로 비교합니다.
- 이미 manifest 소유이고 원하는 상태로 생성된 리소스는 재생성하지 않고 읽기 검증만 합니다. 원격 API가 정규화하는 값과 요청 형식의 차이를 실패 후 덮어쓰기로 해결하지 않습니다.
- 이 환경의 text-embedding-3-small은 GlobalStandard/DataZoneStandard를 보고했습니다. 강사 명령은 `--embedding-sku GlobalStandard`를 명시하며 지원 여부를 다시 확인합니다.
