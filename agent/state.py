from typing import TypedDict


class Tab1State(TypedDict):
    ctmno: str
    tier: str                   # "신규" | "미연결" | "이력"
    data: dict                  # DuckDB fetch 결과
    db_markdown: str            # ① 계약현황 ② 보장현황 즉시 표시 섹션
    hyde_query: str             # HyDE 가상 요약 (RAG 검색 쿼리)
    rag_cases: list             # [{"doc": str, "meta": dict}, ...] 성공 콜 케이스
    rag_products: str           # 상품 설명서 RAG 텍스트
    customer_insight: str       # ReAct 분석 결과 (approach_angle, key_points 등)
    approach_angle: str         # "complement" | "followup" | "new_product"
    needs_product_search: bool  # ReAct: LLM이 추가 상품 문서 필요 판단 시 True
    product_query: str          # ReAct: 추가 검색할 상품 키워드
    final_prompt: str           # 스크립트 생성용 최종 프롬프트 (스트리밍 입력)
