"""실행: uv run streamlit run app/streamlit_app.py"""

from dataclasses import asdict
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from hanbit_assistant.agent import AssistantError
from hanbit_assistant.config import Settings
from hanbit_assistant.ui import SessionRuntime

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
st.set_page_config(page_title="한빛 출장 도우미", page_icon="🧳", layout="wide")
st.title("🧳 한빛 출장 도우미")
st.caption("가상 회사 사규를 찾고, 실제 날씨와 환율을 연결하는 Agent + RAG 실습")

with st.sidebar:
    st.header("이 답변은 어떻게 만들어질까요?")
    st.markdown(
        "**① 질문 이해** · Agent가 필요한 도구를 선택합니다.\n\n"
        "**② 근거 수집** · 사규는 Azure AI Search, 날씨는 Open-Meteo, 환율은 Frankfurter에서 가져옵니다.\n\n"
        "**③ 근거와 함께 답변** · 문서 청크 ID와 도구 실행 내역을 확인합니다."
    )
    st.divider()
    st.warning("한빛 회사와 사규는 교육용 허구입니다. 개인정보·실제 사내 기밀을 입력하지 마세요.")
    st.caption("날씨: 현재 값(미래 출장일 예보 아님) · 환율: 최근 영업일 참고값(수수료 미포함)")

try:
    settings = Settings.from_env()
except ValueError:
    st.info(
        "먼저 저장소의 .env.example을 .env로 복사하고 강사에게 받은 주소·개인 키·인덱스를 입력하세요. 키는 화면이나 Git에 공유하지 마세요."
    )
    st.code(
        "OPENAI_BASE_URL=.../agent-rag/openai/v1\nWORKSHOP_API_KEY=<개인 구독 키>\nAZURE_SEARCH_ENDPOINT=.../agent-rag/search\nAZURE_SEARCH_INDEX=student01\nOPENAI_MODEL=gpt-5.6-terra",
        language="bash",
    )
    st.stop()

if "runtime" not in st.session_state:
    st.session_state.runtime = SessionRuntime(settings)
if "messages" not in st.session_state:
    st.session_state.messages = []
runtime = st.session_state.runtime

with st.sidebar:
    st.caption(f"모델: {settings.model} · 내 인덱스: {settings.search_index}")
    st.caption("세션별 대화 분리 · 원격 응답 저장 끔 · 질문당 도구 최대 6회 / 120초")
    if st.button("새 대화 / 초기화", key="reset_chat", use_container_width=True):
        runtime.close()
        st.session_state.runtime = SessionRuntime(settings)
        st.session_state.messages = []
        st.rerun()
    st.caption(
        "앱은 인덱스를 자동 생성하지 않습니다. 먼저 RAG 노트북의 본인 인덱스 업로드 단계를 완료하세요."
    )


def render_turn(turn):
    # 외부 모델/문서 Markdown을 렌더링하지 않습니다. 이미지 URL을 통한 추적도 방지합니다.
    st.text(turn["text"])
    if turn["sources"]:
        with st.expander(f"검색 근거 · {len(turn['sources'])}개 청크", expanded=False):
            st.caption(
                "검색된 근거입니다. 답변의 [청크 ID]와 대조하세요. Markdown의 page=1은 기본 논리 페이지이며 인쇄 쪽수가 아닙니다."
            )
            for source in turn["sources"]:
                st.text(
                    f"{source['citation']} {source['title']}\n{source['source']} · {source['section']} · page {source['page']}"
                )
                st.text(source["content"][:1200])
                st.divider()
    with st.expander("도구 실행 내역 · 추론 과정이 아닌 실제 호출 기록", expanded=False):
        if turn["tool_events"]:
            st.dataframe(turn["tool_events"], hide_index=True, use_container_width=True)
        else:
            st.caption("이번 응답에는 도구 호출이 없었습니다.")


if not st.session_state.messages:
    st.info(
        "질문 예시: “도쿄 출장 숙박비 한도와 승인 절차를 알려줘.” / “런던 현재 날씨는?” / “100 USD를 KRW로 환산해 줘.”"
    )
    st.caption(
        "사규에서 답을 찾을 수 없으면 확인할 수 없다고 답합니다. 없는 규정을 질문해 보고 근거를 검증해 보세요."
    )

for item in st.session_state.messages:
    with st.chat_message(item["role"]):
        if item["role"] == "user":
            st.text(item["text"])
        else:
            render_turn(item)

prompt = st.chat_input("출장 규정, 현재 날씨, 참고 환율을 질문하세요", max_chars=4000)
if prompt:
    st.session_state.messages.append({"role": "user", "text": prompt})
    with st.chat_message("user"):
        st.text(prompt)
    with st.chat_message("assistant"):
        with st.spinner("필요한 도구와 근거를 확인하고 있습니다…"):
            try:
                turn = asdict(runtime.run(runtime.chat.ask(prompt)))
            except AssistantError as exc:
                turn = {"text": str(exc), "sources": [], "tool_events": []}
            except Exception:  # noqa: BLE001 — do not expose SDK secrets at this UI boundary
                turn = {
                    "text": "앱 실행 중 오류가 발생했습니다. 새 대화를 시작하고 설정을 확인하세요.",
                    "sources": [],
                    "tool_events": [],
                }
        render_turn(turn)
        st.session_state.messages.append({"role": "assistant", **turn})
