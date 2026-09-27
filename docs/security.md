# 보안 경계와 한계

## 실제 경계

`개인 APIM subscription → 전용 API scope → exact route/index guard → APIM managed identity → Foundry/Search`

- 수강생에게 Foundry/Search 관리자 키나 Entra 역할을 주지 않습니다.
- subscription 표시 이름 `student01`~`student10`, `instructor`를 인덱스 경계에 사용합니다. 학생은 APIM 관리 권한이 없으며 이름·scope를 변경할 수 없습니다.
- 인덱스 이름을 단순 prefix로 검사하지 않습니다. REST/OData의 허용된 경로를 정확히 검사합니다.
- 인덱스 전체 목록·서비스 관리·인덱스 삭제·다른 API·원격 응답 조회 경로는 노출하지 않습니다.
- APIM은 입력 Authorization/api-key/구독키를 다운스트림 전에 제거하고 관리 ID로 인증합니다.
- APIM 관리 ID는 전용 Search 범위의 Search Service Contributor + Search Index Data Contributor를 갖습니다. 기존 Foundry 범위의 Cognitive Services OpenAI User는 유지합니다.
- Search 로컬 키 인증은 끄고 Entra 인증을 사용합니다. 학생에게는 APIM 개인 키만 보입니다.

## 모델/도구 제한

- 배포명: `gpt-5.6-terra`, `text-embedding-3-small`만 허용
- `store=false` 강제, `previous_response_id`/`conversation`/서버 응답 조회 금지
- 로컬 function 도구만 허용. hosted web search, code interpreter, 임의 MCP/외부 벡터라이저 금지
- 출력 최대 1500 토큰(앱은 1200), 모델 입력 24000자 등 게이트웨이 제한
- 본문: 모델 256KiB, Search 2MiB; 학생별 분당 60회 요청 제한 (일별 quota 정책은 없음)
- 앱: 사용자 질문 최대 4000자, 도구 최대 6회, 응답 제한 120초, 최대 20턴 후 초기화
- Opaque encrypted reasoning 항목은 stateless Responses 호환을 위해 전달하지만 추론 텍스트로 출력하지 않습니다.

이 제한들은 **정확한 금액 기준 예산 상한이 아닙니다**. 공유 모델의 전체 호출량이나 다른 API의 사용량을 막지 않습니다. 교육 목적의 저비용·소규모 경계이지 악성 사용자에 대한 완전한 멀티테넌트 제품 설계가 아닙니다.

## 데이터와 UI

정책은 허구이며 문서/도구 출력은 지시로 신뢰하지 않습니다. 도구는 고정된 날씨/환율 도메인과 허용 도시/통화만 사용합니다. 임의 URL·shell·파일 읽기 도구는 없습니다. 대화 세션은 사용자별이고 모델/문서의 Markdown 이미지 등을 UI에서 실행하지 않습니다.

`.env`, `.local/`, 실행 노트북은 공개하지 않습니다. 원격 응답 저장은 꺼도 로컬 메모리·비공개 실행 산출물에는 대화가 남을 수 있습니다. 브라우저/OS/조직 프록시 로그는 별도 영역입니다.

## 운영 전 추가로 필요한 것

인증된 사용자 ID와 키 발급/만료 자동화, 개인 키 안전 전달, 강한 테넌트 격리, 문서 ACL, 삭제/버전 동기화, 지속 평가, 조직 네트워크 정책, 관측/로그 보존 정책, 쓰기 도구 승인/감사 등은 추가 설계가 필요합니다. 이 샘플의 인용 ID 검사는 인용의 존재만 확인하며 사실적 함의까지 증명하지 않습니다.
