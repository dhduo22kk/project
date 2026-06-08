"""
Tab1 LangGraph Pipeline

흐름:
  classify → fetch_data → format_db → hyde → rag → analyze
                                                       ↓
                                          needs_product_search?
                                          YES → fetch_extra_products → prepare_prompt
                                          NO  ────────────────────── → prepare_prompt → END

핵심 기술:
  - HyDE (Hypothetical Document Embedding): 가상 성공 요약 → Chroma 검색 품질 향상
  - Dynamic Few-Shot: 현재 고객과 가장 유사한 성공 콜 케이스를 RAG로 동적 검색 → few-shot 예시
  - ReAct lite: analyze_node에서 LLM이 추가 상품 문서 필요 여부를 판단 → 조건부 툴 호출
  - CoT 2단계: analyze(고객 분석) → prepare_prompt(스크립트 생성 프롬프트 구성)

스트리밍: 최종 스크립트 생성은 tab1_handler.stream_tab1()에서 LLM.stream()으로 처리
"""
import json
import logging
from datetime import datetime

import pandas as pd
from langchain_ollama import OllamaLLM, OllamaEmbeddings
from langchain_chroma import Chroma
from langgraph.graph import StateGraph, END

from agent.state import Tab1State
from config.settings import (
    OLLAMA_BASE_URL, LLM_MODEL, EMBED_MODEL, CHROMA_PATH,
    TBL_CUSTOMER, TBL_COVERAGE, TBL_CALL_DETAIL,
    TBL_CONTRACT_HISTORY, TBL_DESIGN_HISTORY,
    TBL_NEW_COVERAGE, TBL_RECOMMENDATION,
    TBL_INELIGIBLE, TBL_SALES_FOCUS, TBL_MSG_HISTORY,
)
from db.manager import query_df, query_one

log = logging.getLogger(__name__)

COVERAGE_LABELS: dict[str, str] = {
    "CANCR_DASCS_AMT":           "암진단비",
    "ISMC_HEART_DSAS_DASCS_AMT": "허혈성심장질환진단비",
    "CRLR_DSAS_DASCS_AMT":       "뇌혈관질환진단비",
    "DSAS_HSP_RLPMI_AMT":        "질병입원실손",
    "DSAS_OTP_RLPMI_AMT":        "질병통원실손",
    "SERI_DEMEN_AMT":            "중증치매",
    "LTRM_RCPR_DGN_RANK4_AMT":  "장기요양진단4급",
    "BDIN_CCA_SUAMT_AMT":        "대인형사합의지원금",
    "LWR_SNRT_CS_AMT":           "변호사선임비용",
    "DRV_PNLTY_AMT":             "운전자벌금",
    "FIRE_PNLTY_AMT":            "화재벌금",
    "USLLF_LBTRS_AMT":           "일상생활배상책임",
}


# ── 공통 유틸 ─────────────────────────────────────────────────────────────────

def _q(sql: str, params: list) -> pd.DataFrame:
    try:
        return query_df(sql, params)
    except Exception as e:
        log.warning(f"쿼리 실패: {e}")
        return pd.DataFrame()


def _fmt_amt(val) -> str:
    try:
        n = int(val or 0)
        return f"{n:,}원" if n > 0 else "**미가입** ⚠️"
    except Exception:
        return "**미가입** ⚠️"


def _sex_label(raw: str) -> str:
    s = str(raw or "")
    if "M" in s:
        return "남"
    if "F" in s:
        return "여"
    return "?"


def _fmt_dt(val) -> str:
    try:
        if pd.isna(val):
            return "?"
        return str(val)[:16]
    except Exception:
        return str(val)[:16]


def _coverage_gaps(cov: dict) -> list[str]:
    return [label for col, label in COVERAGE_LABELS.items() if int(cov.get(col, 0) or 0) == 0]


# ── Node 1: classify ──────────────────────────────────────────────────────────

def classify_node(state: Tab1State) -> dict:
    ctmno = state["ctmno"]
    df = _q(f"SELECT RESULT_CD FROM {TBL_CALL_DETAIL} WHERE CTMNO = ?", [ctmno])
    if df.empty:
        tier = "신규"
    elif all(r in {"결번", "미연결", "타인통화"} for r in df["RESULT_CD"].tolist()):
        tier = "미연결"
    else:
        tier = "이력"
    log.info(f"[classify] {ctmno} → {tier}")
    return {"tier": tier}


# ── Node 2: fetch_data ────────────────────────────────────────────────────────

def fetch_data_node(state: Tab1State) -> dict:
    ctmno, tier = state["ctmno"], state["tier"]
    data: dict = {"tier": tier, "ctmno": ctmno}

    cust_df = _q(f"SELECT * FROM {TBL_CUSTOMER} WHERE CTMNO = ?", [ctmno])
    data["customer"] = cust_df.iloc[0].to_dict() if not cust_df.empty else {}

    cov_df = _q(f"SELECT * FROM {TBL_COVERAGE} WHERE CTMNO = ?", [ctmno])
    data["coverage"] = cov_df.iloc[0].to_dict() if not cov_df.empty else {}

    data["recommendations"] = _q(
        f"""
        SELECT r.REC_RANK, r.REC_GDCD, r.REC_GDNM, r.REC_POCT
        FROM {TBL_RECOMMENDATION} r
        WHERE r.CTMNO = ?
          AND NOT EXISTS (
              SELECT 1 FROM {TBL_INELIGIBLE} i
              WHERE i.CTMNO = ? AND i.GDCD = r.REC_GDCD
          )
        ORDER BY r.REC_RANK LIMIT 3
        """,
        [ctmno, ctmno],
    )

    ym = datetime.now().strftime("%Y%m")
    sf = query_one(f"SELECT FOCUS_TEXT FROM {TBL_SALES_FOCUS} WHERE FOCUS_YM = ?", [ym])
    data["sales_focus"] = sf[0] if sf else ""

    if tier in ("미연결", "이력"):
        data["calls"] = _q(
            f"SELECT * FROM {TBL_CALL_DETAIL} WHERE CTMNO = ? ORDER BY CALL_DT DESC", [ctmno]
        )
        data["contracts"] = _q(
            f"SELECT * FROM {TBL_CONTRACT_HISTORY} WHERE CTMNO = ? ORDER BY INS_ST DESC", [ctmno]
        )
        data["new_coverage"] = _q(
            f"SELECT * FROM {TBL_NEW_COVERAGE} WHERE CTMNO = ? ORDER BY CVR_START_DT DESC", [ctmno]
        )

    if tier == "이력":
        data["designs"] = _q(
            f"SELECT * FROM {TBL_DESIGN_HISTORY} WHERE CTMNO = ? ORDER BY DESIGN_DT DESC", [ctmno]
        )
        data["msg_history"] = _q(
            f"SELECT SEND_DT, MSG_CONTENT, MSG_TYPE FROM {TBL_MSG_HISTORY} WHERE CTMNO = ? ORDER BY SEND_DT DESC LIMIT 5",
            [ctmno],
        )

    return {"data": data}


# ── Node 3: format_db ─────────────────────────────────────────────────────────

def format_db_node(state: Tab1State) -> dict:
    tier = state["tier"]
    data = state["data"]
    cust = data.get("customer", {})
    ctmno = data["ctmno"]

    age = cust.get("CTM_AGE", "?")
    sex = _sex_label(cust.get("CTM_SEX", ""))
    region = cust.get("REGION", "?")
    campaign = cust.get("INFLOW_CAMPAIGN_NM") or "미확인"
    seg = cust.get("INP_SEG", "")

    parts: list[str] = [
        f"## 고객번호: {ctmno}  |  {age}세 {sex}  |  {region}  |  유입: {campaign}  |  **{tier} 고객** ({seg})\n"
    ]

    if tier in ("미연결", "이력"):
        contracts = data.get("contracts", pd.DataFrame())
        new_cov = data.get("new_coverage", pd.DataFrame())
        parts.append(_contract_summary_md(contracts, new_cov))
        parts.append("")

        calls = data.get("calls", pd.DataFrame())
        time_hint = _recommend_call_time(calls)
        if time_hint:
            parts.append(time_hint)
        if tier == "미연결":
            parts.append(f"- ⚠️ 미연결 시도: {len(calls)}회 (연결 성공 없음)")
        parts.append("")
        parts.append(_call_timeline_md(calls))
        parts.append("")

    parts.append(_coverage_md(data.get("coverage", {})))

    recs = data.get("recommendations", pd.DataFrame())
    if not recs.empty:
        parts.append("\n### ML 추천 상품")
        for _, r in recs.iterrows():
            pct = f"{float(r['REC_POCT']):.1%}" if r["REC_POCT"] is not None else ""
            parts.append(f"- {r['REC_RANK']}위: {r['REC_GDNM']} ({pct})")

    return {"db_markdown": "\n".join(parts)}


def _contract_summary_md(contracts: pd.DataFrame, new_cov: pd.DataFrame) -> str:
    if contracts.empty:
        return "### 계약 현황\n- 계약 없음"
    cnt = len(contracts)
    total_prm = int(contracts["AP_PRM"].fillna(0).sum())
    last_dt = contracts["INS_ST"].dropna().max()
    last_str = str(last_dt)[:7] if pd.notna(last_dt) else "?"
    lines = [
        "### 계약 현황",
        f"- 가입 상품 수: {cnt}개",
        f"- 월 납입 보험료: {total_prm:,}원",
        f"- 최근 가입 시점: {last_str}",
    ]
    if new_cov is not None and not new_cov.empty:
        nc = ", ".join(new_cov["CVR_NM"].dropna().tolist())
        lines.append(f"- 🆕 최근 3개월 신규 담보: {nc}")
    return "\n".join(lines)


def _call_timeline_md(calls: pd.DataFrame) -> str:
    if calls.empty:
        return ""
    lines = ["### 통화 이력"]
    for _, row in calls.head(10).iterrows():
        dt = _fmt_dt(row.get("CALL_DT"))
        result = str(row.get("RESULT_CD", ""))
        dur = int(row.get("CALL_DURATION", 0) or 0)
        dur_str = f"{dur}초 (대화 진행됨)" if dur >= 30 else f"{dur}초"
        lines.append(f"- {dt} | {result} | {dur_str}")
    return "\n".join(lines)


def _recommend_call_time(calls: pd.DataFrame) -> str:
    if calls.empty:
        return ""
    connected = calls[calls["RESULT_CD"] == "연결성공"]
    if connected.empty:
        return ""
    try:
        hours = connected["CALL_DT"].dropna().apply(
            lambda x: x.hour if hasattr(x, "hour") else None
        ).dropna()
        if hours.empty:
            return ""
        best = int(hours.mode().iloc[0])
        return f"- 추천 통화 시간: {best}시~{best+1}시 (과거 연결 성공 기준)"
    except Exception:
        return ""


def _coverage_md(cov: dict) -> str:
    lines = ["### 보장 현황"]
    for col, label in COVERAGE_LABELS.items():
        lines.append(f"- {label}: {_fmt_amt(cov.get(col, 0))}")
    return "\n".join(lines)


# ── Node 4: hyde ──────────────────────────────────────────────────────────────

_HYDE_PROMPT = """\
아래 고객 정보를 보고, 이 고객과 유사한 상황에서 성공했던 보험 TM 상담의 핵심을 2~3문장으로 요약하세요.
실제로 일어난 상담처럼 과거형으로 작성하세요. 요약 텍스트만 출력하고 다른 설명은 쓰지 마세요.

[고객 정보]
나이: {age}세, 성별: {sex}, 유입캠페인: {campaign}
주요 미보장 담보: {gaps}

요약:"""


def hyde_node(state: Tab1State) -> dict:
    data = state["data"]
    cust = data.get("customer", {})
    cov = data.get("coverage", {})

    age = cust.get("CTM_AGE", "?")
    sex = "남성" if "M" in str(cust.get("CTM_SEX", "")) else "여성"
    campaign = cust.get("INFLOW_CAMPAIGN_NM") or "캠페인미확인"
    gaps = ", ".join(_coverage_gaps(cov)[:4]) or "정보 없음"

    try:
        llm = OllamaLLM(model=LLM_MODEL, base_url=OLLAMA_BASE_URL, temperature=0)
        hyde_query = llm.invoke(_HYDE_PROMPT.format(age=age, sex=sex, campaign=campaign, gaps=gaps))
        hyde_query = hyde_query.strip()
    except Exception as e:
        log.warning(f"HyDE 생성 실패, 폴백 사용: {e}")
        hyde_query = f"[고객: {age}세 {sex}, {campaign}] {gaps} 보험 상담 성공"

    log.info(f"[hyde] query={hyde_query[:60]}...")
    return {"hyde_query": hyde_query}


# ── Node 5: rag ───────────────────────────────────────────────────────────────

def rag_node(state: Tab1State) -> dict:
    emb = OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_BASE_URL)
    calls_col = Chroma(
        collection_name="calls",
        embedding_function=emb,
        persist_directory=str(CHROMA_PATH),
    )
    products_col = Chroma(
        collection_name="products",
        embedding_function=emb,
        persist_directory=str(CHROMA_PATH),
    )

    ctmno = state["ctmno"]
    tier = state["tier"]
    hyde_query = state["hyde_query"]
    data = state["data"]
    recs = data.get("recommendations", pd.DataFrame())
    rec_names = recs["REC_GDNM"].dropna().tolist() if not recs.empty else []

    # 성공 콜 케이스 검색
    rag_cases: list[dict] = []
    try:
        if tier == "이력":
            # 이력 고객: 해당 고객 과거 콜 직접 조회 (우호적 우선 정렬)
            res = calls_col.get(where={"CTMNO": ctmno})
            docs = res.get("documents", [])
            metas = res.get("metadatas", [])
            paired = sorted(
                zip(docs, metas),
                key=lambda x: (0 if x[1].get("SENTIMENT") == "우호적" else 1),
            )
            rag_cases = [{"doc": d, "meta": m} for d, m in paired[:3]]
        else:
            # 신규/미연결: HyDE 쿼리로 유사 성공 콜 검색 (연결성공 + 우호적 우선)
            res = calls_col.query(
                query_texts=[hyde_query],
                n_results=3,
                where={"$and": [
                    {"RESULT_CD": {"$eq": "연결성공"}},
                    {"SENTIMENT": {"$eq": "우호적"}},
                ]},
            )
            docs  = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            # 폴백: 연결성공만
            if not docs:
                res   = calls_col.query(query_texts=[hyde_query], n_results=3,
                                        where={"RESULT_CD": {"$eq": "연결성공"}})
                docs  = (res.get("documents") or [[]])[0]
                metas = (res.get("metadatas") or [[]])[0]
            rag_cases = [{"doc": d, "meta": m} for d, m in zip(docs, metas)]
    except Exception as e:
        log.warning(f"RAG calls 조회 실패: {e}")

    # 상품 문서 검색
    rag_products = ""
    try:
        if rec_names:
            query = " ".join(rec_names) + " 보험 상품 특징 특약 납입기간"
            res = products_col.query(query_texts=[query], n_results=3)
            pdocs = (res.get("documents") or [[]])[0]
            if pdocs:
                rag_products = "[상품 설명서]\n" + "\n---\n".join(pdocs[:2])
    except Exception as e:
        log.warning(f"RAG products 조회 실패: {e}")

    log.info(f"[rag] cases={len(rag_cases)}, products={'있음' if rag_products else '없음'}")
    return {"rag_cases": rag_cases, "rag_products": rag_products}


# ── Node 6: analyze (ReAct lite) ─────────────────────────────────────────────

_ANALYZE_PROMPT = """\
당신은 보험 TM 상담 전략 전문가입니다. 아래 고객 정보와 유사 성공 콜 사례를 분석하여 JSON으로 응답하세요.

[고객 정보]
{customer_info}

[ML 추천 상품]
{rec_info}

[유사 성공 콜 요약]
{case_summaries}

아래 JSON만 반환하세요 (다른 텍스트 없이):
{{
  "approach_angle": "complement 또는 followup 또는 new_product",
  "key_points": ["이 고객에게 강조할 핵심 포인트 2~3개"],
  "insight": "이 각도로 접근하는 이유와 주의사항 1~2문장",
  "needs_product_search": true 또는 false,
  "product_query": "추가로 검색할 상품 키워드 (needs_product_search가 true일 때만, 아니면 빈 문자열)"
}}

approach_angle 기준:
- complement: 기존 계약 있음 → 담보 gap 보완
- followup: 설계이력만 있음 → 미체결 팔로업
- new_product: 이력 없음 → 신상품 공략"""


def analyze_node(state: Tab1State) -> dict:
    data = state["data"]
    tier = state["tier"]
    cust = data.get("customer", {})
    rag_cases = state["rag_cases"]

    age = cust.get("CTM_AGE", "?")
    sex = "남성" if "M" in str(cust.get("CTM_SEX", "")) else "여성"
    region = cust.get("REGION", "?")
    campaign = cust.get("INFLOW_CAMPAIGN_NM") or "미확인"
    cov = data.get("coverage", {})
    gaps = ", ".join(_coverage_gaps(cov)[:6]) or "정보 없음"

    cust_lines = [
        f"나이: {age}세, 성별: {sex}, 지역: {region}",
        f"유입: {campaign}, 분류: {tier}",
        f"주요 미보장: {gaps}",
    ]
    if tier == "미연결":
        calls = data.get("calls", pd.DataFrame())
        cust_lines.append(f"미연결 시도: {len(calls)}회")
    elif tier == "이력":
        calls = data.get("calls", pd.DataFrame())
        connected = calls[calls["RESULT_CD"] == "연결성공"] if not calls.empty else pd.DataFrame()
        cust_lines.append(f"과거 통화: 연결 {len(connected)}회 / 총 {len(calls)}회")
        msg = data.get("msg_history", pd.DataFrame())
        if not msg.empty:
            last = msg.iloc[0]
            cust_lines.append(f"최근 문자({str(last.get('SEND_DT',''))[:10]}): {str(last.get('MSG_CONTENT',''))[:60]}")

    recs = data.get("recommendations", pd.DataFrame())
    rec_info = "\n".join(f"- {r['REC_RANK']}위: {r['REC_GDNM']}" for _, r in recs.iterrows()) if not recs.empty else "없음"

    case_summaries = "\n".join(
        f"- ({c['meta'].get('SENTIMENT','')}, 키워드: {c['meta'].get('KEYWORDS','')}) {c['doc']}"
        for c in rag_cases[:3]
    ) or "없음"

    try:
        llm = OllamaLLM(
            model=LLM_MODEL, base_url=OLLAMA_BASE_URL,
            temperature=0, format="json",
        )
        raw = llm.invoke(_ANALYZE_PROMPT.format(
            customer_info="\n".join(cust_lines),
            rec_info=rec_info,
            case_summaries=case_summaries,
        ))
        parsed = json.loads(raw)
    except Exception as e:
        log.warning(f"analyze_node LLM/JSON 실패, 룰베이스 폴백: {e}")
        contracts = data.get("contracts", pd.DataFrame())
        designs = data.get("designs", pd.DataFrame())
        angle = "complement" if not contracts.empty else ("followup" if not designs.empty else "new_product")
        parsed = {
            "approach_angle": angle,
            "key_points": [f"주요 미보장: {gaps}"],
            "insight": "기본 접근 전략 적용",
            "needs_product_search": False,
            "product_query": "",
        }

    log.info(f"[analyze] angle={parsed.get('approach_angle')}, needs_search={parsed.get('needs_product_search')}")
    return {
        "customer_insight": json.dumps(parsed, ensure_ascii=False),
        "approach_angle":        parsed.get("approach_angle", "new_product"),
        "needs_product_search":  bool(parsed.get("needs_product_search", False)),
        "product_query":         parsed.get("product_query", ""),
    }


# ── Node 7: fetch_extra_products (조건부) ────────────────────────────────────

def fetch_extra_products_node(state: Tab1State) -> dict:
    query = state.get("product_query", "")
    if not query:
        return {}
    try:
        emb = OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_BASE_URL)
        col = Chroma(collection_name="products", embedding_function=emb,
                     persist_directory=str(CHROMA_PATH))
        res = col.query(query_texts=[query], n_results=2)
        docs = (res.get("documents") or [[]])[0]
        if docs:
            extra = "\n[추가 상품 자료]\n" + "\n---\n".join(docs)
            return {"rag_products": state.get("rag_products", "") + extra}
    except Exception as e:
        log.warning(f"추가 상품 검색 실패: {e}")
    return {}


# ── Node 8: prepare_prompt ────────────────────────────────────────────────────

_SCRIPT_PROMPT = """\
당신은 보험 TM 콜센터 전문 어시스턴트입니다.
아래 고객 분석 결과와 성공 콜 예시를 참고하여 상담사가 바로 사용할 맞춤 스크립트를 작성하세요.

[고객 분석 결과]
{customer_insight_text}

[성공 콜 예시 — 유사 고객 실제 상담 원문 (어투·접근방식 참고)]
{few_shot_examples}

[보장 현황 (gap = 미가입)]
{coverage_info}

[상품 참고 자료]
{product_docs}

[이번 달 영업 포커스]
{sales_focus}

[작성 지침]
- 성공 콜 예시의 어투와 접근 방식을 자연스럽게 반영하세요.
- 실제 담보 gap을 구체적으로 언급하세요.
- 과장하거나 단정적인 표현을 쓰지 마세요.
- 스크립트는 자연스러운 한국어 TM 말투로, 3~5문장으로 작성하세요.

[출력 형식]
### ③ 추천 상품 및 맞춤 스크립트

**접근 각도**: {approach_angle_label}

**추천 상품**: 상품명

**핵심 포인트**:
- 포인트1
- 포인트2

**이의 처리**: 고객 거부 시 대응 방법 한 줄

**스크립트**:
"안녕하세요, 고객님. ..."

---
**고능률 상담사 접근 키워드**: #키워드1 #키워드2 #키워드3 #키워드4
(성공 콜 사례에서 추출한 핵심 접근 포인트)
"""

_ANGLE_LABELS = {
    "complement":  "담보 Gap 보완 (기존 계약 고객)",
    "followup":    "설계 팔로업 (미체결 고객)",
    "new_product": "신규 상품 공략",
}


def prepare_prompt_node(state: Tab1State) -> dict:
    data = state["data"]
    cov = data.get("coverage", {})
    rag_cases = state["rag_cases"]

    # 성공 콜 few-shot 예시: MASKED_TEXT 원문 활용
    few_shot_parts = []
    for i, case in enumerate(rag_cases[:2], 1):
        meta = case.get("meta", {})
        masked = str(meta.get("MASKED_TEXT", "")).strip()[:600]
        kw = meta.get("KEYWORDS", "")
        sentiment = meta.get("SENTIMENT", "")
        if masked:
            few_shot_parts.append(
                f"[예시 {i}] 키워드: {kw} | 고객태도: {sentiment}\n{masked}"
            )
    few_shot_text = "\n\n".join(few_shot_parts) if few_shot_parts else "없음 (DB 조회 정보 기반으로 작성)"

    # 보장 현황 텍스트
    cov_lines = []
    for col, label in COVERAGE_LABELS.items():
        amt = int(cov.get(col, 0) or 0)
        status = f"{amt:,}원" if amt > 0 else "미가입 (gap)"
        cov_lines.append(f"- {label}: {status}")

    # 고객 분석 결과 파싱
    try:
        insight_dict = json.loads(state.get("customer_insight", "{}"))
        key_points = "\n".join(f"- {p}" for p in insight_dict.get("key_points", []))
        insight_text = f"접근 각도: {insight_dict.get('approach_angle', '')}\n핵심 포인트:\n{key_points}\n분석: {insight_dict.get('insight', '')}"
    except Exception:
        insight_text = state.get("customer_insight", "")

    prompt = _SCRIPT_PROMPT.format(
        customer_insight_text=insight_text,
        few_shot_examples=few_shot_text,
        coverage_info="\n".join(cov_lines),
        product_docs=state.get("rag_products", "") or "없음",
        sales_focus=data.get("sales_focus", "") or "없음",
        approach_angle_label=_ANGLE_LABELS.get(state.get("approach_angle", "new_product"), "신규 공략"),
    )
    return {"final_prompt": prompt}


# ── 조건부 엣지 라우터 ────────────────────────────────────────────────────────

def _route_after_analyze(state: Tab1State) -> str:
    return "fetch_extra_products" if state.get("needs_product_search") else "prepare_prompt"


# ── 그래프 컴파일 ─────────────────────────────────────────────────────────────

def build_tab1_graph():
    g = StateGraph(Tab1State)

    g.add_node("classify",              classify_node)
    g.add_node("fetch_data",            fetch_data_node)
    g.add_node("format_db",             format_db_node)
    g.add_node("hyde",                  hyde_node)
    g.add_node("rag",                   rag_node)
    g.add_node("analyze",               analyze_node)
    g.add_node("fetch_extra_products",  fetch_extra_products_node)
    g.add_node("prepare_prompt",        prepare_prompt_node)

    g.set_entry_point("classify")
    g.add_edge("classify",             "fetch_data")
    g.add_edge("fetch_data",           "format_db")
    g.add_edge("format_db",            "hyde")
    g.add_edge("hyde",                 "rag")
    g.add_edge("rag",                  "analyze")
    g.add_conditional_edges(
        "analyze",
        _route_after_analyze,
        {"fetch_extra_products": "fetch_extra_products", "prepare_prompt": "prepare_prompt"},
    )
    g.add_edge("fetch_extra_products", "prepare_prompt")
    g.add_edge("prepare_prompt",       END)

    return g.compile()


TAB1_GRAPH = build_tab1_graph()
