"""
Tab1: 콜 전 준비 핸들러

stream_tab1(ctmno) → Generator[(db_markdown, script_accumulated)]
  - 첫 yield: DB 섹션(계약/보장 현황) 완성, script=""
  - 이후 yield: DB 섹션 동일, LLM 스크립트 점진적 누적
"""
import sys
import logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from langchain_ollama import OllamaLLM, OllamaEmbeddings
from langchain_chroma import Chroma

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


# ── 3분기 분류 ────────────────────────────────────────────────────────────────

def _classify(ctmno: str) -> str:
    df = query_df(
        f"SELECT RESULT_CD FROM {TBL_CALL_DETAIL} WHERE CTMNO = ?", [ctmno]
    )
    if df.empty:
        return "신규"
    no_connect = {"결번", "미연결", "타인통화"}
    if all(r in no_connect for r in df["RESULT_CD"].tolist()):
        return "미연결"
    return "이력"


# ── DuckDB 데이터 조회 ────────────────────────────────────────────────────────

def _q(sql: str, params: list):
    try:
        return query_df(sql, params)
    except Exception as e:
        log.warning(f"쿼리 실패: {e}")
        return pd.DataFrame()


def _fetch_data(ctmno: str, tier: str) -> dict:
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
        ORDER BY r.REC_RANK
        LIMIT 3
        """,
        [ctmno, ctmno],
    )

    ym = datetime.now().strftime("%Y%m")
    sf = query_one(f"SELECT FOCUS_TEXT FROM {TBL_SALES_FOCUS} WHERE FOCUS_YM = ?", [ym])
    data["sales_focus"] = sf[0] if sf else ""

    if tier in ("미연결", "이력"):
        data["calls"] = _q(
            f"SELECT * FROM {TBL_CALL_DETAIL} WHERE CTMNO = ? ORDER BY CALL_DT DESC",
            [ctmno],
        )
        data["contracts"] = _q(
            f"SELECT * FROM {TBL_CONTRACT_HISTORY} WHERE CTMNO = ? ORDER BY INS_ST DESC",
            [ctmno],
        )
        data["new_coverage"] = _q(
            f"SELECT * FROM {TBL_NEW_COVERAGE} WHERE CTMNO = ? ORDER BY CVR_START_DT DESC",
            [ctmno],
        )

    if tier == "이력":
        data["designs"] = _q(
            f"SELECT * FROM {TBL_DESIGN_HISTORY} WHERE CTMNO = ? ORDER BY DESIGN_DT DESC",
            [ctmno],
        )
        data["msg_history"] = _q(
            f"SELECT SEND_DT, MSG_CONTENT, MSG_TYPE FROM {TBL_MSG_HISTORY} WHERE CTMNO = ? ORDER BY SEND_DT DESC LIMIT 5",
            [ctmno],
        )

    return data


# ── 마크다운 포맷 ─────────────────────────────────────────────────────────────

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


def _coverage_md(cov: dict) -> str:
    lines = ["### 보장 현황"]
    for col, label in COVERAGE_LABELS.items():
        amt = int(cov.get(col, 0) or 0)
        lines.append(f"- {label}: {_fmt_amt(amt)}")
    return "\n".join(lines)


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
        hours = connected["CALL_DT"].dropna().apply(lambda x: x.hour if hasattr(x, "hour") else None).dropna()
        if hours.empty:
            return ""
        best = int(hours.mode().iloc[0])
        return f"- 추천 통화 시간: {best}시~{best+1}시 (과거 연결 성공 기준)"
    except Exception:
        return ""


def _format_db_section(tier: str, data: dict) -> str:
    cust = data.get("customer", {})
    age = cust.get("CTM_AGE", "?")
    sex = _sex_label(cust.get("CTM_SEX", ""))
    region = cust.get("REGION", "?")
    campaign = cust.get("INFLOW_CAMPAIGN_NM") or "미확인"
    seg = cust.get("INP_SEG", "")
    ctmno = data["ctmno"]

    parts: list[str] = []
    parts.append(
        f"## 고객번호: {ctmno}  |  {age}세 {sex}  |  {region}  |  유입: {campaign}  |  **{tier} 고객** ({seg})\n"
    )

    if tier in ("미연결", "이력"):
        contracts = data.get("contracts", pd.DataFrame())
        new_cov   = data.get("new_coverage", pd.DataFrame())
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

    return "\n".join(parts)


# ── Chroma RAG ────────────────────────────────────────────────────────────────

def _make_collections() -> tuple:
    emb = OllamaEmbeddings(model=EMBED_MODEL, base_url=OLLAMA_BASE_URL)
    calls = Chroma(
        collection_name="calls",
        embedding_function=emb,
        persist_directory=str(CHROMA_PATH),
    )
    products = Chroma(
        collection_name="products",
        embedding_function=emb,
        persist_directory=str(CHROMA_PATH),
    )
    return calls, products


def _rag_calls_direct(col, ctmno: str) -> str:
    try:
        res = col.get(where={"CTMNO": ctmno})
        docs = res.get("documents", [])
        metas = res.get("metadatas", [])
        if not docs:
            return ""
        lines = ["[과거 통화 요약]"]
        for doc, meta in zip(docs[:5], metas[:5]):
            dt = str(meta.get("CALL_DT", ""))[:10]
            sentiment = meta.get("SENTIMENT", "")
            kw = meta.get("KEYWORDS", "")
            lines.append(f"- ({dt}, {sentiment}, 키워드: {kw}) {doc}")
        return "\n".join(lines)
    except Exception as e:
        log.debug(f"Chroma calls.get 오류: {e}")
        return ""


def _rag_calls_similar(col, age, sex_raw: str, campaign_nm: str) -> str:
    try:
        sex = _sex_label(sex_raw)
        query = f"[고객: {age}세 {sex}, {campaign_nm}] 보험 상담 성공"
        res = col.query(
            query_texts=[query],
            n_results=3,
            where={"RESULT_CD": "연결성공"},
        )
        docs = (res.get("documents") or [[]])[0]
        if not docs:
            res = col.query(query_texts=[query], n_results=3)
            docs = (res.get("documents") or [[]])[0]
        if not docs:
            return ""
        return "[유사 성공 콜 참고]\n" + "\n".join(f"- {d}" for d in docs)
    except Exception as e:
        log.debug(f"Chroma calls.query 오류: {e}")
        return ""


def _rag_products(col, rec_names: list[str]) -> str:
    if not rec_names:
        return ""
    try:
        query = " ".join(rec_names) + " 보험 상품 특징 특약 납입기간"
        res = col.query(query_texts=[query], n_results=4)
        docs = (res.get("documents") or [[]])[0]
        if not docs:
            return ""
        return "[상품 설명서 참고]\n" + "\n---\n".join(docs[:3])
    except Exception as e:
        log.debug(f"Chroma products.query 오류: {e}")
        return ""


def _get_rag(ctmno: str, tier: str, data: dict) -> str:
    try:
        calls_col, products_col = _make_collections()
        cust = data.get("customer", {})
        age = cust.get("CTM_AGE", "?")
        sex_raw = str(cust.get("CTM_SEX", ""))
        campaign_nm = cust.get("INFLOW_CAMPAIGN_NM") or "캠페인미확인"
        recs = data.get("recommendations", pd.DataFrame())
        rec_names = recs["REC_GDNM"].dropna().tolist() if not recs.empty else []

        parts: list[str] = []
        if tier == "이력":
            parts.append(_rag_calls_direct(calls_col, ctmno))
        else:
            parts.append(_rag_calls_similar(calls_col, age, sex_raw, campaign_nm))
        parts.append(_rag_products(products_col, rec_names))
        return "\n\n".join(p for p in parts if p)
    except Exception as e:
        log.warning(f"RAG 조회 실패: {e}")
        return ""


# ── LLM 프롬프트 ──────────────────────────────────────────────────────────────

_ANGLE_GUIDES = {
    "complement":  "고객에게 기존 계약이 있으므로, 보장 gap(미가입 담보)을 보완하는 방향으로 추천하세요.",
    "followup":    "고객이 설계까지 진행했으나 미체결 상태입니다. 기존 설계 건의 팔로업 방향으로 작성하세요.",
    "new_product": "신규 또는 미체결 고객입니다. 핵심 담보 gap과 주력 상품을 중심으로 작성하세요.",
}

_PROMPT = """\
당신은 보험 TM 콜센터 전문 어시스턴트입니다.
아래 고객 정보를 바탕으로 상담사가 콜 전에 바로 활용할 맞춤 스크립트와 상품 추천을 작성하세요.

[고객 정보]
{customer_info}

[보장 현황 (gap = 미가입)]
{coverage_info}

[ML 추천 상품]
{rec_info}

[참고 자료 — 과거 통화/상품 설명서]
{rag_context}

[이번 달 영업 포커스]
{sales_focus}

[작성 지침]
{angle_guide}
- 실제 담보 gap을 구체적으로 언급하세요.
- 과장하거나 단정적인 표현을 쓰지 마세요.
- 스크립트는 자연스러운 한국어 TM 말투로, 3~5문장으로 작성하세요.

[출력 형식]
### ③ 추천 상품 및 맞춤 스크립트
**추천 상품**: 상품명
**추천 근거**: 1~2줄
**스크립트**:
"안녕하세요, 고객님. ..."
"""


def _coverage_for_prompt(cov: dict) -> str:
    lines = []
    for col, label in COVERAGE_LABELS.items():
        amt = int(cov.get(col, 0) or 0)
        status = f"{amt:,}원" if amt > 0 else "미가입 (gap)"
        lines.append(f"- {label}: {status}")
    return "\n".join(lines)


def _get_script_angle(data: dict) -> str:
    contracts = data.get("contracts", pd.DataFrame())
    designs   = data.get("designs", pd.DataFrame())
    if not contracts.empty:
        return "complement"
    if not designs.empty:
        return "followup"
    return "new_product"


def _build_prompt(tier: str, data: dict, rag: str) -> str:
    cust = data.get("customer", {})
    age = cust.get("CTM_AGE", "?")
    sex = "남성" if "M" in str(cust.get("CTM_SEX", "")) else "여성"
    region = cust.get("REGION", "?")
    campaign = cust.get("INFLOW_CAMPAIGN_NM") or "미확인"
    seg = cust.get("INP_SEG", "")

    cust_lines = [
        f"- 나이: {age}세, 성별: {sex}, 지역: {region}",
        f"- 유입경로: {campaign}, 고객유형: {seg}, 분류: {tier} 고객",
    ]

    if tier == "미연결":
        calls = data.get("calls", pd.DataFrame())
        cust_lines.append(f"- 미연결 시도: {len(calls)}회 (연결 성공 없음)")

    elif tier == "이력":
        calls = data.get("calls", pd.DataFrame())
        connected = calls[calls["RESULT_CD"] == "연결성공"] if not calls.empty else pd.DataFrame()
        cust_lines.append(f"- 과거 통화: 연결 {len(connected)}회 / 총 {len(calls)}회")
        msg = data.get("msg_history", pd.DataFrame())
        if not msg.empty:
            last = msg.iloc[0]
            dt = str(last.get("SEND_DT", ""))[:10]
            content = str(last.get("MSG_CONTENT", ""))[:80]
            cust_lines.append(f"- 최근 문자발송({dt}): {content}")

    recs = data.get("recommendations", pd.DataFrame())
    if recs.empty:
        rec_info = "ML 추천 없음 (RAG 참고)"
    else:
        rec_info = "\n".join(
            f"- {r['REC_RANK']}위: {r['REC_GDNM']}" for _, r in recs.iterrows()
        )

    angle = _get_script_angle(data)

    return _PROMPT.format(
        customer_info="\n".join(cust_lines),
        coverage_info=_coverage_for_prompt(data.get("coverage", {})),
        rec_info=rec_info,
        rag_context=rag or "없음",
        sales_focus=data.get("sales_focus", "") or "없음",
        angle_guide=_ANGLE_GUIDES[angle],
    )


# ── 공개 인터페이스 ───────────────────────────────────────────────────────────

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
        tier = _classify(ctmno)
        data = _fetch_data(ctmno, tier)
        db_md = _format_db_section(tier, data)
        yield db_md, "⏳ 스크립트 생성 중..."

        rag = _get_rag(ctmno, tier, data)
        prompt = _build_prompt(tier, data, rag)

        llm = OllamaLLM(
            model=LLM_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0.3,
        )
        accumulated = ""
        for chunk in llm.stream(prompt):
            accumulated += chunk
            yield db_md, accumulated

    except Exception as e:
        log.error(f"Tab1 오류 [{ctmno}]: {e}", exc_info=True)
        yield f"오류가 발생했습니다: {e}", ""
