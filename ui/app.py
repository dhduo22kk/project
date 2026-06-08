"""
Gradio 메인 앱

실행:
    python ui/app.py

탭 구성:
    Tab1: 콜 전 준비 (상담사)       — 고객번호 조회 → DB 현황 즉시 표시 → LLM 스크립트 스트리밍
    Tab2: 캠페인 추천 대상 생성 (본사 스태프) — 캠페인 선택 → 폼 → Excel 다운로드
"""
import sys
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import gradio as gr

from config.settings import SERVER_HOST, SERVER_PORT, DUCKDB_PATH
from agent.tab1_handler import stream_tab1
from agent.campaign import (
    get_campaign_list,
    get_prev_campaign_stats,
    has_past_performance_data,
    has_activity_data,
    extract_campaign_list,
    to_excel_tempfile,
    parse_age_ranges,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _campaign_choices() -> list[str]:
    df = get_campaign_list()
    choices = ["[신규 캠페인]"]
    for _, row in df.iterrows():
        nm   = row.get("CAMPAIGN_NM", "")
        typ  = row.get("CAMPAIGN_TYPE", "")
        choices.append(f"{nm} ({typ})" if typ else nm)
    return choices


def _duckdb_mtime() -> str:
    try:
        p = Path(DUCKDB_PATH)
        if p.exists():
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
            return f"마지막 갱신: {mtime.strftime('%Y-%m-%d %H:%M')}"
        return "mart.db 없음"
    except Exception:
        return "갱신 시각 확인 불가"


def _parse_campaign_nm(choice: str) -> str:
    if not choice or choice == "[신규 캠페인]":
        return ""
    # "캠페인명 (TM)" → "캠페인명"
    if choice.endswith(")") and " (" in choice:
        return choice.rsplit(" (", 1)[0]
    return choice


# ── Tab1 핸들러 ───────────────────────────────────────────────────────────────

def on_query(ctmno: str):
    """Tab1 조회 버튼 핸들러. Generator."""
    yield from stream_tab1(ctmno)


# ── Tab2 핸들러 ───────────────────────────────────────────────────────────────

def on_campaign_select(choice: str):
    """캠페인 선택 시 직전 통계 카드 업데이트."""
    nm = _parse_campaign_nm(choice)
    if not nm:
        return gr.update(value=""), gr.update(choices=["활성도 기반"], value="활성도 기반")

    stats = get_prev_campaign_stats(nm)
    has_perf = has_past_performance_data(nm)
    has_act  = has_activity_data()

    # 직전 캠페인 비교 카드
    if stats:
        card = (
            f"### 직전 캠페인 실적 (참고치 — ML 예측 아님)\n"
            f"- 배정 수: {stats['total']:,}명\n"
            f"- 체결 수: {stats['success']:,}명\n"
            f"- 체결율: {stats['success_rate']}%\n"
            f"- 평균 체결 보험료: {stats['avg_prm']:,}원"
        )
    else:
        card = ""

    # 추출 방식 선택지 (데이터 없으면 비활성화)
    strategy_choices = []
    if has_act:
        strategy_choices.append("활성도 기반")
    if has_perf:
        strategy_choices.append("과거 실적 기반")
    if not strategy_choices:
        strategy_choices = ["활성도 기반"]

    return gr.update(value=card), gr.update(choices=strategy_choices, value=strategy_choices[0])


def on_extract(
    campaign_choice: str,
    is_new: str,
    product_types: list,
    channels: list,
    gender: str,
    age_chips: list,
    target_count: float,
    strategy: str,
):
    """Tab2 추출 버튼 핸들러."""
    nm = _parse_campaign_nm(campaign_choice or "")
    age_range = parse_age_ranges(age_chips or [])

    conditions = {
        "campaign_nm":    nm,
        "is_new_campaign": "새로" in (is_new or ""),
        "product_types":  product_types or [],
        "channel":        channels or [],
        "gender": (
            None if not gender or gender == "전체"
            else ("1.M" if gender == "남성" else "2.F")
        ),
        "age_range":    age_range,
        "target_count": int(target_count or 1000),
        "strategy": (
            "past_performance" if "실적" in (strategy or "")
            else "activity_based"
        ),
    }

    try:
        df = extract_campaign_list(conditions)
        if df.empty:
            return gr.update(visible=False), "추출 결과가 없습니다. 조건을 확인하세요."
        fpath = to_excel_tempfile(df)
        msg = f"✅ {len(df):,}명 추출 완료"
        return gr.update(value=fpath, visible=True), msg
    except Exception as e:
        log.error(f"캠페인 추출 오류: {e}", exc_info=True)
        return gr.update(visible=False), f"오류: {e}"


def on_refresh_db():
    return _duckdb_mtime()


# ── Gradio UI ─────────────────────────────────────────────────────────────────

def build_ui() -> gr.Blocks:
    with gr.Blocks(
        title="AI 상담 에이전트",
        theme=gr.themes.Soft(),
        css=".gap-label { color: #e53e3e; font-weight: bold; }",
    ) as demo:
        gr.Markdown("# AI 상담 에이전트")

        with gr.Row():
            db_status = gr.Markdown(_duckdb_mtime(), elem_id="db-status")
            refresh_btn = gr.Button("DuckDB 갱신 확인", size="sm", scale=0)
        refresh_btn.click(on_refresh_db, outputs=db_status)

        with gr.Tabs():

            # ── Tab 1 ─────────────────────────────────────────────────────────
            with gr.TabItem("Tab1: 콜 전 준비 (상담사)"):
                with gr.Row():
                    ctmno_input = gr.Textbox(
                        label="고객번호 (CTMNO)",
                        placeholder="예: 123456789",
                        scale=5,
                    )
                    query_btn = gr.Button("조회", variant="primary", scale=1)

                db_section = gr.Markdown(
                    label="① 계약 현황  ②  보장 현황",
                    value="",
                    elem_id="db-section",
                )
                script_output = gr.Textbox(
                    label="③ 추천 상품 및 맞춤 스크립트",
                    lines=18,
                    interactive=False,
                    show_copy_button=True,
                )

                query_btn.click(
                    on_query,
                    inputs=[ctmno_input],
                    outputs=[db_section, script_output],
                )
                ctmno_input.submit(
                    on_query,
                    inputs=[ctmno_input],
                    outputs=[db_section, script_output],
                )

            # ── Tab 2 ─────────────────────────────────────────────────────────
            with gr.TabItem("Tab2: 캠페인 추천 대상 생성 (본사 스태프)"):
                with gr.Row():

                    # 좌측: 캠페인 목록
                    with gr.Column(scale=1, min_width=260):
                        gr.Markdown("### 캠페인 선택")
                        campaign_radio = gr.Radio(
                            choices=_campaign_choices(),
                            label="",
                            value="[신규 캠페인]",
                        )

                    # 우측: 폼 Q&A
                    with gr.Column(scale=2):

                        gr.Markdown("### Step 0: 캠페인 특성")
                        with gr.Row():
                            product_types = gr.CheckboxGroup(
                                choices=["건강보험", "암보험", "운전자보험", "실손", "뇌심혈관", "치매", "기타"],
                                label="상품 유형",
                            )
                        with gr.Row():
                            channels = gr.CheckboxGroup(
                                choices=["TM", "CM", "POM"],
                                label="채널",
                            )
                        with gr.Row():
                            gender_radio = gr.Radio(
                                choices=["전체", "여성", "남성"],
                                value="전체",
                                label="타겟 성별",
                            )
                            age_chips = gr.CheckboxGroup(
                                choices=["20대", "30대", "40대", "50대", "60대+"],
                                label="타겟 연령대",
                            )

                        gr.Markdown("### Step 1: 신규 캠페인 여부")
                        is_new_radio = gr.Radio(
                            choices=["아니오, 기존 리스트 활용", "네, 새로 만들게요"],
                            value="아니오, 기존 리스트 활용",
                            label="",
                        )

                        gr.Markdown("### Step 2: 목표 인원수")
                        target_count = gr.Number(
                            value=1000,
                            label="인원수",
                            precision=0,
                            minimum=1,
                            maximum=300000,
                        )

                        gr.Markdown("### Step 3: 추출 방식")
                        strategy_radio = gr.Radio(
                            choices=["활성도 기반", "과거 실적 기반"],
                            value="활성도 기반",
                            label="",
                            info="'활성도 기반': 최근 6개월 연결성공·배정이력 고객 | '과거 실적 기반': 동일 캠페인 성공 세그먼트 재현 (이력 없으면 비활성)",
                        )

                        gr.Markdown("### Step 4: 직전 캠페인 비교")
                        prev_stats_md = gr.Markdown(
                            value="",
                            label="",
                        )

                        extract_btn = gr.Button("추출", variant="primary", size="lg")
                        extract_result_md = gr.Markdown("")
                        result_file = gr.File(
                            label="Excel 다운로드 (CTMNO)",
                            visible=False,
                            file_types=[".xlsx"],
                        )

                # 이벤트 연결
                campaign_radio.change(
                    on_campaign_select,
                    inputs=[campaign_radio],
                    outputs=[prev_stats_md, strategy_radio],
                )

                extract_btn.click(
                    on_extract,
                    inputs=[
                        campaign_radio,
                        is_new_radio,
                        product_types,
                        channels,
                        gender_radio,
                        age_chips,
                        target_count,
                        strategy_radio,
                    ],
                    outputs=[result_file, extract_result_md],
                )

    return demo


# ── 진입점 ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from db.manager import init_db
    init_db()
    demo = build_ui()
    demo.launch(
        server_name=SERVER_HOST,
        server_port=SERVER_PORT,
        show_error=True,
    )
