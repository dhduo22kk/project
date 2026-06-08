"""
Tab1: 콜 전 준비 핸들러 (스트리밍 퍼블릭 인터페이스)

내부 파이프라인 (agent/graph.py):
  classify → fetch_data → format_db → hyde → rag → analyze → [fetch_extra_products] → prepare_prompt

  - HyDE: 가상 성공 요약 생성 → Chroma 검색 품질 향상
  - Dynamic Few-Shot: 현재 고객과 가장 유사한 성공 콜을 RAG로 동적 검색 → few-shot 예시
  - ReAct lite: analyze_node에서 LLM이 추가 상품 문서 필요 여부 판단 → 조건부 툴 호출
  - CoT 2단계: analyze(고객 분석) → prepare_prompt(최종 프롬프트 구성)

외부 인터페이스:
  stream_tab1(ctmno) → Generator[(db_markdown, script_accumulated)]
    - 첫 yield: DB 섹션 완성, script="⏳ 스크립트 생성 중..."
    - 이후 yield: DB 섹션 동일, LLM 스크립트 점진적 누적
"""
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_ollama import OllamaLLM

from config.settings import OLLAMA_BASE_URL, LLM_MODEL
from agent.graph import TAB1_GRAPH
from agent.state import Tab1State

log = logging.getLogger(__name__)

_INITIAL_STATE: Tab1State = {
    "ctmno":               "",
    "tier":                "",
    "data":                {},
    "db_markdown":         "",
    "hyde_query":          "",
    "rag_cases":           [],
    "rag_products":        "",
    "customer_insight":    "",
    "approach_angle":      "new_product",
    "needs_product_search": False,
    "product_query":       "",
    "final_prompt":        "",
}


def stream_tab1(ctmno: str):
    """
    Tab1 전체 흐름. Gradio generator 함수.
    Yields: (db_markdown: str, script_accumulated: str)
    """
    ctmno = (ctmno or "").strip()
    if not ctmno:
        yield "고객번호를 입력하세요.", ""
        return

    try:
        # LangGraph 파이프라인 실행 (classify → ... → prepare_prompt)
        state = TAB1_GRAPH.invoke({**_INITIAL_STATE, "ctmno": ctmno})

        db_md = state["db_markdown"]
        final_prompt = state["final_prompt"]

        # DB 섹션 즉시 표시
        yield db_md, "⏳ 스크립트 생성 중..."

        # CoT 2단계: final_prompt 기반 스크립트 스트리밍
        llm = OllamaLLM(
            model=LLM_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0.3,
        )
        accumulated = ""
        for chunk in llm.stream(final_prompt):
            accumulated += chunk
            yield db_md, accumulated

    except Exception as e:
        log.error(f"Tab1 오류 [{ctmno}]: {e}", exc_info=True)
        yield f"오류가 발생했습니다: {e}", ""
