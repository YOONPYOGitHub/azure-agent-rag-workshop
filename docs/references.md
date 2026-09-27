# 출처 · API · 이전 교육과의 연결

확인일: 2026-09-27. SDK 버전은 `uv.lock`의 실제 설치 조합을 기준으로 합니다. 문서의 최신 코드와 클래스 이름은 달라질 수 있으므로 잠금 파일을 유지하세요.

## 공식 기술 자료
- [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
- [Foundry Responses API와 로컬 실행형 에이전트](https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/responses-api)
- [Azure AI Search 벡터 검색](https://learn.microsoft.com/en-us/azure/search/vector-search-overview)
- [Azure AI Search 하이브리드 검색](https://learn.microsoft.com/en-us/azure/search/hybrid-search-overview)
- [APIM managed identity 정책](https://learn.microsoft.com/en-us/azure/api-management/authentication-managed-identity-policy)
- [APIM subscription rate-limit](https://learn.microsoft.com/en-us/azure/api-management/rate-limit-policy)
- [Azure Retail Prices API](https://prices.azure.com/api/retail/prices)

## 실제 호출할 외부 API

| API | 이 샘플의 엔드포인트 | 출처/제약 |
|---|---|---|
| Open-Meteo | `https://api.open-meteo.com/v1/forecast` | 현재 날씨, 좌표/도시 allowlist, 비상업 교육 콘텐츠 |
| Frankfurter | `https://api.frankfurter.dev/v1/latest` | 실제 동작 확인된 v1 호환 경로, 최근 영업일 참고 환율 |

[Open-Meteo 약관](https://open-meteo.com/en/terms)은 교육 콘텐츠를 비상업 사용 예로 안내합니다. 무료 API 제한은 분당 600/시간당 5000/일 10000 미만이며 [CC BY 4.0](https://open-meteo.com/en/licence) 출처 표시가 필요합니다. 상업 제품/홍보 용도로 옮길 때는 유료 플랜/약관을 다시 검토하세요.

[Frankfurter 문서](https://frankfurter.dev/)는 v2 API도 제공합니다. v1 `rates` 객체와 v2 응답 형식을 섞어 파싱하지 마세요. 이 코드의 v1 JPY→KRW 실호출을 확인했습니다. 환율 기준일을 답변에 포함하고 은행 수수료/실제 정산과 구분합니다.

## 검색용 문서

**기본 과정:** `data/policies/`의 가상 한빛테크 정책 9개. 워크숍 작성자가 새로 작성한 MIT 자료이며 외부 회사 정책을 사실처럼 재사용하지 않습니다.

**실제로 찾아 포함한 공개 샘플:** [Zava Company Overview](../data/external-samples/Zava_Company_Overview.md). Microsoft Azure-Samples 원본의 commit `3f4a21f03ae3d565aca37cc300e3d38b0c7b582a`에서 가져왔고 MIT 라이선스를 함께 보존했습니다. 별도 가상 회사이므로 기본 인덱스에는 혼합하지 않습니다.

PDF 확장에 사용할 수 있는 공개 원본:
- [Benefit_Options.pdf](https://github.com/Azure-Samples/azure-search-openai-demo/blob/3f4a21f03ae3d565aca37cc300e3d38b0c7b582a/data/Benefit_Options.pdf)
- [employee_handbook.pdf](https://github.com/Azure-Samples/azure-search-openai-demo/blob/3f4a21f03ae3d565aca37cc300e3d38b0c7b582a/data/employee_handbook.pdf)
- [upstream MIT License](https://github.com/Azure-Samples/azure-search-openai-demo/blob/3f4a21f03ae3d565aca37cc300e3d38b0c7b582a/LICENSE)

PDF는 링크만 제공하며 기본 파서는 Markdown 전용입니다. PDF 실습을 추가할 때 페이지별 추출·OCR 필요 여부·출처 페이지·원문 라이선스 유지부터 설계하세요.

## 이전 repo → 이번 과정

| 이전 자료 | 이어지는 개념 | 이번 변경 |
|---|---|---|
| [azure-ai-workshop](https://github.com/YOONPYOGitHub/azure-ai-workshop) | 모델 호출·프롬프트·Responses·기초 tool/RAG | 하나의 출장 시나리오로 연결, 실행형 앱까지 완성 |
| [aoai-function-calling](https://github.com/YOONPYOGitHub/aoai-function-calling) | 날씨·환율 JSON Schema와 수동 호출 | Responses 형식 수동 루프 → Agent Framework 자동 루프 |
| [aoai-rag-pipeline](https://github.com/YOONPYOGitHub/aoai-rag-pipeline) | 청킹·임베딩·BM25/벡터·근거 인용 | 검색을 Agent 도구로 연결, 개인 인덱스/API 권한 경계 |

과거 Chat Completions의 `tool_calls` 메시지 형식을 Responses의 `function_call` / `function_call_output`과 섞지 않습니다. Microsoft Agent Framework의 현재 `OpenAIChatClient`는 Responses를 사용합니다. 이 과정은 Semantic Kernel/AutoGen 구버전 코드를 그대로 사용하는 과정이 아닙니다.
