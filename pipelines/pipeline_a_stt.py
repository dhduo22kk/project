"""
Pipeline A: STT 인덱싱 (1회성, resume 지원)

실행:
    python pipelines/pipeline_a_stt.py

처리 흐름:
    WAV(CALL_ID.wav) → faster-whisper STT
    → Regex 마스킹(utils/masking.py)
    → Qwen3.6 통합 호출 (마스킹+분석 → JSON)
    → nomic-embed-text 임베딩
    → Chroma calls 컬렉션

Chroma embedded_text 포맷:
    "[고객: {age}세 {sex}, {campaign_nm}] {summary}"

resume: CALL_ID 단위 collection.get(ids=[call_id]) → 존재하면 skip
소요 시간: 약 41~83시간 (5천 건 × 30~60초)
"""

import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from faster_whisper import WhisperModel
from langchain_ollama import OllamaLLM, OllamaEmbeddings
from langchain_chroma import Chroma

from config.settings import (
    WAV_DIR, WHISPER_MODEL_PATH, OLLAMA_BASE_URL,
    LLM_MODEL, EMBED_MODEL, CHROMA_PATH,
    TBL_CALL_DETAIL, TBL_COVERAGE, TBL_CUSTOMER,
)
from db.manager import query_df
from utils.masking import mask_pii_regex

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

COLLECTION_NAME = "calls"

# LLM 프롬프트: 마스킹 + 분석 단일 호출
_PROMPT = """\
당신은 보험 콜센터 상담 녹취 분석 전문가입니다.
아래 녹취 텍스트에서 개인정보를 추가 마스킹하고 분석 결과를 JSON으로 반환하세요.

[마스킹 규칙]
- 고객/상담사 이름 → [이름]
- 도로명/지번 주소 → [주소]
- 기타 개인식별 정보 → [개인정보]

[분석 기준]
- sentiment: 고객의 통화 중 태도 ("우호적" 또는 "비우호적", 체결 여부와 무관)
- keywords: 통화 핵심 단어 최대 5개 (상품명, 담보명, 고객 관심사 등)
- summary: 상담 내용 핵심 2~3문장 요약

반드시 아래 JSON 형식만 반환하세요 (다른 텍스트 없이):
{{
  "masked_text": "마스킹 완료된 전체 녹취 텍스트",
  "sentiment": "우호적",
  "keywords": ["키워드1", "키워드2"],
  "summary": "상담 요약 2~3문장"
}}

[녹취 텍스트]
{text}"""


def _load_models():
    whisper = WhisperModel(
        WHISPER_MODEL_PATH,
        device="cuda",
        compute_type="float16",
    )
    llm = OllamaLLM(
        model=LLM_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0,
        format="json",
    )
    embeddings = OllamaEmbeddings(
        model=EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
    )
    collection = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(CHROMA_PATH),
    )
    return whisper, llm, collection


def _transcribe(whisper: WhisperModel, wav_path: Path) -> str:
    segments, _ = whisper.transcribe(str(wav_path), language="ko", beam_size=5)
    return " ".join(seg.text for seg in segments).strip()


def _analyze(llm: OllamaLLM, text: str) -> dict:
    raw = llm.invoke(_PROMPT.format(text=text))
    return json.loads(raw)


def _get_call_meta(call_id: str) -> dict | None:
    """CALL_ID → CTMNO + 통화 메타 + 보장금액 12개 + 고객 인구통계."""
    df = query_df(
        f"""
        SELECT
            c.CTMNO, c.CALL_DT, c.CALL_DURATION, c.RESULT_CD,
            c.CAMPAIGN_NM, c.CHANNEL_TYPE,
            cu.CTM_AGE, cu.CTM_SEX,
            cv.CANCR_DASCS_AMT,
            cv.ISMC_HEART_DSAS_DASCS_AMT,
            cv.CRLR_DSAS_DASCS_AMT,
            cv.DSAS_HSP_RLPMI_AMT,
            cv.DSAS_OTP_RLPMI_AMT,
            cv.SERI_DEMEN_AMT,
            cv.LTRM_RCPR_DGN_RANK4_AMT,
            cv.BDIN_CCA_SUAMT_AMT,
            cv.LWR_SNRT_CS_AMT,
            cv.DRV_PNLTY_AMT,
            cv.FIRE_PNLTY_AMT,
            cv.USLLF_LBTRS_AMT
        FROM {TBL_CALL_DETAIL} c
        LEFT JOIN {TBL_CUSTOMER} cu ON c.CTMNO = cu.CTMNO
        LEFT JOIN {TBL_COVERAGE} cv ON c.CTMNO = cv.CTMNO
        WHERE c.CALL_ID = ?
        """,
        params=[call_id],
    )
    if df.empty:
        return None
    return df.iloc[0].to_dict()


def _build_embedded_text(meta: dict, summary: str) -> str:
    age = meta.get("CTM_AGE") or "?"
    sex = meta.get("CTM_SEX") or "?"
    campaign_nm = meta.get("CAMPAIGN_NM") or "캠페인미확인"
    return f"[고객: {age}세 {sex}, {campaign_nm}] {summary}"


def _build_metadata(call_id: str, meta: dict, analysis: dict) -> dict:
    """Chroma metadata는 scalar(str/int/float/bool)만 허용. list 불가."""
    coverage_cols = [
        "CANCR_DASCS_AMT", "ISMC_HEART_DSAS_DASCS_AMT", "CRLR_DSAS_DASCS_AMT",
        "DSAS_HSP_RLPMI_AMT", "DSAS_OTP_RLPMI_AMT", "SERI_DEMEN_AMT",
        "LTRM_RCPR_DGN_RANK4_AMT", "BDIN_CCA_SUAMT_AMT", "LWR_SNRT_CS_AMT",
        "DRV_PNLTY_AMT", "FIRE_PNLTY_AMT", "USLLF_LBTRS_AMT",
    ]
    m = {
        "CALL_ID":       call_id,
        "CTMNO":         str(meta.get("CTMNO") or ""),
        "RESULT_CD":     str(meta.get("RESULT_CD") or ""),
        "CALL_DURATION": int(meta.get("CALL_DURATION") or 0),
        "CAMPAIGN_NM":   str(meta.get("CAMPAIGN_NM") or "캠페인미확인"),
        "CHANNEL_TYPE":  str(meta.get("CHANNEL_TYPE") or ""),
        "SENTIMENT":     str(analysis.get("sentiment", "")),
        "KEYWORDS":      ",".join(analysis.get("keywords", [])),
        "MASKED_TEXT":   str(analysis.get("masked_text", "")),
    }
    for col in coverage_cols:
        val = meta.get(col)
        m[col] = int(val) if val is not None else 0
    return m


def run():
    wav_files = sorted(WAV_DIR.glob("*.wav"))
    if not wav_files:
        log.warning(f"WAV 파일 없음: {WAV_DIR}")
        return

    log.info(f"=== Pipeline A 시작: {len(wav_files)}건 ===")
    whisper, llm, collection = _load_models()

    done = skipped = failed = 0
    for wav_path in wav_files:
        call_id = wav_path.stem
        try:
            # resume: 이미 인덱싱된 CALL_ID 스킵
            if collection.get(ids=[call_id])["ids"]:
                skipped += 1
                continue

            # DuckDB 메타 조회 (CALL_ID → CTMNO 매핑)
            meta = _get_call_meta(call_id)
            if meta is None:
                log.warning(f"  SKIP  {call_id}: DuckDB 매핑 없음")
                skipped += 1
                continue

            # STT
            raw_text = _transcribe(whisper, wav_path)
            if not raw_text:
                log.warning(f"  SKIP  {call_id}: STT 결과 없음")
                skipped += 1
                continue

            # 1단계: Regex 마스킹
            regex_masked = mask_pii_regex(raw_text)

            # 2단계: LLM 마스킹+분석 단일 호출
            analysis = _analyze(llm, regex_masked)

            # Chroma 저장
            embedded_text = _build_embedded_text(meta, analysis.get("summary", ""))
            metadata = _build_metadata(call_id, meta, analysis)

            collection.add(
                ids=[call_id],
                documents=[embedded_text],
                metadatas=[metadata],
            )

            done += 1
            if done % 100 == 0:
                log.info(f"  진행: {done}/{len(wav_files)} 완료 (스킵={skipped}, 실패={failed})")

        except Exception as e:
            log.error(f"  ERROR {call_id}: {e}")
            failed += 1

    log.info(f"=== Pipeline A 완료: 처리={done}, 스킵={skipped}, 실패={failed} ===")


if __name__ == "__main__":
    run()
