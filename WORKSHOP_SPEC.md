# 구현 계약

- 한국어, 약 6시간(휴식 포함), Codespaces 기본 / 로컬 VS Code 대체, Python 3.11 + uv, Microsoft Agent Framework 기반 단일 에이전트.
- App Service 배포는 필수 완료 조건이 아니다. 개인 키 설정 → doctor → 노트북 → start → 비공개 포트에서 동작 확인이 기본 경로다.
- 앱은 LLM만 / 고정 RAG / Agent 학습 모드를 제공한다. RAG 기준선의 keyword/vector/hybrid 검색 비교, 근거·실행 이벤트·경과 시간 표시. 모드 변경 시 대화 분리.
- 노트북은 예측→실행→관찰→변경→설명 실험과 학습자 연습·선택 해설을 포함한다. 실습 편의성·동시 실행 품질 우선이며 최저 비용만을 목표로 하지 않는다.
- 가상 한빛테크 출장 도우미: 사내 출장 정책 RAG + Open-Meteo 날씨 + Frankfurter 환율. 실제 예약/결제 없음.
- 기존 gpt-5.6-terra 배포명 그대로 사용; 신규 text-embedding-3-small 1536차원.
- 실제 클라이언트 경로: 수강생 Codespace/로컬 앱 → 개인별 APIM 키 → Foundry 모델 / 전용 Azure AI Search.
- 수강생 10명 Azure 로그인 불필요, student01..student10 인덱스. 서버 APIM에서 키별 인덱스 경계 강제. 공유 admin key 배포 금지.
- 새 전용 RG의 Search Basic 1 partition/1 replica. 가용성 SLA를 목표로 하는 운영 서비스 아님. 종료 후 삭제할 때까지 과금.
- 기존 공유 APIM /openai 정책 변경 금지. 새 /agent-rag 전용 API, 10개 수강생 subscription + instructor 1개.
- OPENAI_BASE_URL=<gateway>/agent-rag/openai/v1 ; AZURE_SEARCH_ENDPOINT=<gateway>/agent-rag/search ; WORKSHOP_API_KEY=개인키 ; AZURE_SEARCH_INDEX=student01.
- 개인키를 Ocp-Apim-Subscription-Key 헤더에 전달. APIM MI로 다운스트림 인증, 입력 Authorization/api-key 제거.
- notebooks/: 개념과 실행 가능한 교육 셀. src/hanbit_assistant/: 재사용 코드. app/: 실제 챗봇. docs/: 학생·강사·보안·비용 가이드. infra/: 재현가능한 배포 및 철거. data/policies/: 가상 교육용 문서.
- 노트북에서 asyncio.run 대신 top-level await. 출력/비밀 제거 후 commit. 외부 서비스 실패 시 가짜 결과 fallback 금지.
- public repo에 실제 키/테넌트 토큰/수강생 개인정보/대화 로그 금지. 배포 세부·실습키 묶음은 .local/ 또는 별도 private 로컬 경로.
