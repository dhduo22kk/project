# Project: AI Consultation Agent

## Purpose
TM/CM 채널 전사 고객 DB(~30만 명)를 통합 활용하여,
① 상담사가 콜 전 고객 맞춤 스크립트/상품 추천을 즉시 조회하고,
② 본사 스태프(기획자/운영자)가 대화형으로 캠페인 고객 리스트를 추출하고 마케팅 업무를 효율화하는 AI Agent.

### 부서 미션과의 연결
- **부서 미션**: TM/CM/SFP 전사 고객 DB 통합 관리 및 효율화
- **이 프로젝트**: DB 통합 기반으로 채널별 분산된 고객 리스트 생성 업무를 AI Agent로 일원화
  - TM: 캠페인 고객 리스트 생성 + 콜 전 스크립트 지원
  - CM: 갱신 가능성 예측 결과를 활용한 마케팅 비용 절감 (불필요 접촉 제외)
  - 향후 SFP 확장 가능

### 기존 상품추천시스템 대비 개선 포인트
| | 기존 시스템 | 이 프로젝트 |
|---|---|---|
| 추천 근거 | 유사 고객 가입 이력만 (ML) | 가입 이력 + 담보 gap + 과거 통화 맥락 + 캠페인 패턴 |
| 출력 형태 | 상품명 + 고정 텍스트 | 왜 이 상품인지 근거 + 어떻게 말할지 스크립트 |
| 상담 활용 | 맥락 없어 사실상 미사용 | 콜 전 즉시 활용 가능한 형태로 출력 |
→ "추천 결과를 상담사가 실제로 쓸 수 있게 만드는 것"이 핵심 가치

### 핵심 사용 목적
1. **콜 전 준비 (상담사)** — 고객 조회 → 1차/2차 DB 자동 분기 → 맞춤 스크립트 + 상품 추천 + 과거 통화 요약
2. **영업지원 Agent (본사 스태프)** — 캠페인 고객 리스트 추출(Excel) + 캠페인 성과 조회 + 녹취 기반 스크립트 생성 + 신상품 정보 조회

### 사용자 구분
- **상담사** → Tab1(콜 전 준비)만 사용
- **본사 스태프(기획자/운영자)** → Tab2(영업지원 Agent)만 사용

### UI 구현 및 레거시 연동
- **기본 구현**: Gradio UI (사내망 IP 접근, server_name="0.0.0.0")
- **레거시 연동 참고**: 기존 상담사 화면에 상품추천 결과(상품명/텍스트) 표시 구조 존재.
  향후 Gradio API로 AI 추천 결과값을 레거시 UI에 주입/연동하는 방식으로 확장 가능.

### 데이터 규모 및 현실 제약
- **전체 고객**: ~30만 명 (Oracle)
- **WAV 녹취 보유**: ~5천 건 (소수) — 녹취 없는 고객이 대다수
- **콜드스타트**: 인구통계(나이/성별/지역/등록일)만 존재하는 신규 고객 → 벡터 검색 불필요, SQL 필터로 처리

### 입력 데이터
- WAV 녹취 파일 (평균 3분, ~500~700 토큰/건) + Oracle DB 쿼리 결과 DataFrame으로 매핑
- Oracle DB 메타데이터: 통화시간, 체결여부, 과거할당경험, 설계여부 + 다수 컬럼
- LLM 분석 생성값: 긍부정여부, 키워드, 상담 요약
- 내부 문서: 상품정보(DOCX/PPTX/PDF), 가입이력, TM채널 유사고객 이력

## Tech Stack

| 역할 | 선택 | 비고 |
|------|------|------|
| STT | faster-whisper large-v3 | 한국어 최고 정확도, GPU 가속 |
| LLM 서버 | Ollama (latest) | GGUF 모델 서빙 |
| LLM 모델 | Qwen3.6-27B-Q4_K_M | ~16.8GB, KV캐시 여유 ~23GB |
| 비전 LLM | 미정 (Qwen2-VL 계열 경량) | 문서 이미지 → 마크다운 변환용, 인덱싱 시에만 사용 |
| 임베딩 모델 | nomic-embed-text (Ollama) | 별도 패키지 없이 Ollama로 통일 |
| 벡터DB | Chroma (chromadb) | 로컬, 서버 불필요 |
| 분석 DB | DuckDB | Oracle 마트 → 인프로세스 OLAP, 서버 불필요 |
| Agent | LangGraph | 멀티턴 대화 히스토리 포함 |
| LLM 연동 | langchain-ollama | Ollama OpenAI 호환 API |
| UI | Gradio | 사내망 IP 접근 허용 (server_name="0.0.0.0") |
| DB 연결 | cx_Oracle | 서버 기설치, 마트 배치 쿼리용 |
| 문서 파싱 | pymupdf4llm / mammoth / python-pptx | PDF/DOCX/PPTX → 마크다운 변환 |

## Target Environment (폐쇄망 서버)

- OS: Ubuntu x64
- Python: 3.10
- CUDA: 12.4
- GPU VRAM: 40GB
- 인터넷: 없음 (완전 폐쇄망)

## Deployment Constraints

- 오픈망 → 폐쇄망 파일 반입: 망간 파일 전송 시스템 경유
- 반입 형식: `tar.gz` (개별 파일 2GB 초과 시 분할, 각 파트 확장자 반드시 `.tar.gz`)
- 오픈망 PC: Windows, 관리자 권한 없음
- **LangChain Hub / LangSmith 사용 불가** — 폐쇄망에서 HTTP 통신 불가, 의존성 제거

## Bundle 다운로드 (Colab)

`colab_bundle_download.py` — Colab에서 실행, server_env.txt 필요
`colab_model_download.py` — GGUF 모델 다운로드 + tar.gz 분할

```python
!python colab_bundle_download.py   # server_env.txt 같이 업로드
!python colab_model_download.py
```

### 번들 포함 패키지 (신규 설치 대상)

```
# STT / LLM
faster-whisper
ctranslate2          # CUDA 포함 Linux wheel (~400MB)

# LangChain / Agent
langchain-core
langchain
langchain-ollama
langchain-chroma     # Chroma 벡터스토어 연동 (langchain 0.2+에서 community에서 분리)
# langchain-community 제외 — aiohttp 충돌, 역할이 langchain-ollama/langchain-chroma로 대체됨
langgraph
langgraph-checkpoint-sqlite  # 멀티턴 대화 세션 영속성
ollama               # Python 클라이언트 (langsmith 제외)

# 벡터DB
chromadb

# 분석 DB
duckdb

# 문서 파싱
pymupdf4llm          # PDF → 마크다운 (표 구조 보존)
mammoth              # DOCX → 마크다운
python-pptx          # PPTX 슬라이드 텍스트 추출
python-docx          # DOCX 보조

# UI
gradio
openpyxl              # Excel 출력 (캠페인 리스트 다운로드, pandas.to_excel 의존성)

# Ollama 바이너리 / 모델 (별도 반입)
ollama-linux-amd64.tar.zst   # v0.24.0+, .tgz 지원 중단됨
nomic-embed-text              # Ollama 임베딩 모델
비전 LLM GGUF (미정)          # 문서 이미지 변환용
```

### 폐쇄망 서버 기설치 패키지 (다운로드 불필요)

torch 2.6.0+cu124, transformers, cx_Oracle, pandas, numpy, scipy 등.
전체 목록: `server_env.txt` 참조.

## 폐쇄망 설치 순서

```bash
# 패키지 번들
cat ai_bundle_part*.tar.gz > full.tar.gz   # 분할된 경우
tar -xzf ai_bundle.tar.gz                  # 단일 파일인 경우
chmod +x install.sh && ./install.sh

# GGUF 모델 (Qwen3.6)
cat model_part*.tar.gz > model_full.tar.gz
tar -xzf model_full.tar.gz
ollama create mymodel -f /path/to/Modelfile

# 서비스 시작
ollama serve
```

## System Architecture (확정)

### 배치 파이프라인 A: STT 인덱싱 (1회성, resume 지원)

```
WAV 파일 (파일명 = CALL_ID.wav → Path.stem으로 파싱)
    ↓
[매핑] CALL_ID → tbl_call_detail (DuckDB) → CTMNO + 통화시간/체결여부/캠페인명 (1-hop)
    + tbl_coverage (DuckDB) → 보장분석 대분류 담보금액 12개 JOIN
    ↓
[STT Node] faster-whisper large-v3 → 녹취 원문 텍스트
    ↓
[마스킹 + 분석 통합 Node] 개인정보 비식별화 + 분석을 Qwen3.6 단일 호출로 처리
    1단계 Regex (Python): 전화번호/주민번호/계좌번호/카드번호 → [전화번호] 등 패턴 치환
    2단계 LLM (Qwen3.6): Regex 처리 텍스트 입력 → JSON 출력
        {
          "masked_text": "이름/주소 등 비정형 식별정보 마스킹된 텍스트",
          "sentiment": "우호적" | "비우호적",   ← 고객 태도 기준 (체결여부와 별개)
          "keywords": ["키워드1", ..., "키워드5"],
          "summary": "상담 요약"
        }
    ↓
[Index Node] nomic-embed-text → 요약 텍스트 임베딩
    ↓
[Chroma - calls 컬렉션]
    - document: 요약 텍스트 (임베딩 대상)
    - metadata: 마스킹된 원문, CALL_ID, 고객번호, 체결여부, 통화시간, 우호적여부,
                키워드(comma-separated string), 캠페인명, 보장분석 대분류 담보금액 12개
    ※ resume: CALL_ID 단위로 collection.get(ids=[call_id]) 체크 → 존재하면 skip
```

### 배치 파이프라인 B: 문서 인덱싱 (1회성, resume 지원)

```
내부 문서 (DOCX / PPTX / PDF)
    ↓
[텍스트 추출]
    ├─ PDF  → pymupdf4llm → 마크다운
    ├─ DOCX → mammoth → 마크다운
    └─ PPTX → python-pptx → 슬라이드별 마크다운
    ↓
[이미지 처리 — 이미지 포함 문서만]
    비전 LLM 로드 (Qwen3.6 언로드 후 순차 실행)
    → 이미지 → 마크다운 텍스트 변환
    → 비전 LLM 언로드
    ↓
[Index Node] nomic-embed-text → 임베딩
    ↓
[Chroma - products 컬렉션] 상품정보 / 내부 문서
    ※ resume: 문서명 기준 collection.get() 체크 → 존재하면 skip
```

### 배치 파이프라인 C: DuckDB 마트 갱신 (매일 cron 자동 실행)

```
Oracle DB (cx_Oracle) — 이력 로그 테이블 원본
    ↓
도메인별 추출 쿼리 실행 (사용자 사전 작성)
    ↓
DuckDB 도메인 테이블로 저장 (로컬, 인프로세스)
※ 갱신 방식: 별도 파일(mart_new.db)에 TRUNCATE&INSERT 후 atomic rename → 갱신 중 쿼리 블로킹 방지

[DuckDB 테이블 구성]
    tbl_call_detail       — 통화이력 (CALL_ID + CTMNO, 1차/2차 분기 핵심)
                            ※ 결번/무응답 포함 1건이라도 있으면 2차 DB로 분기
    tbl_contract_history  — 계약이력 (고객번호 기준, 체결내역 + 보험료)
                            ※ 보험료 합계는 에이전트가 집계 쿼리로 조회
    tbl_campaign_history  — 캠페인이력 + 배정이력 통합 (고객번호 기준)
                            ※ 유입 캠페인명 조회, 문자발송이력 포함
    tbl_design_history    — 설계이력 (고객번호 기준)
    tbl_customer          — 고객 기본정보 + 유입캠페인명 (인구통계만)
                            ※ Oracle 신규 마트 필요: CUS_CTM + GDREC_ORIGIN_MAIN_FIN_PRED LEFT JOIN
                            ※ 담보금액/계약/설계 컬럼 제외 → 각 전용 테이블에서 조회
                            ※ 신규 고객(계약 없음) 포함, 전체 ~30만 명
    tbl_coverage          — 보장분석 대분류 담보금액 wide (고객번호 기준)
                            ※ 12개 컬럼 (암진단비, 뇌혈관질환진단비 등), 스크립트 생성용
                            ※ 계약 없는 신규 고객은 전체 null
    tbl_coverage_detail   — 담보코드 단위 상세 금액 long (고객번호 × 담보코드)
                            ※ LIKE 검색용 ("2대질병치료비 있는 고객" 등 자유 질의)
    tbl_cvr_group_map     — 담보코드 → 커스텀 그룹명 매핑
                            ※ LLM 초안 생성 + 전문가 검수로 구축, 별도 1회성 스크립트
                            ※ 스키마: CVR_CD, CVR_GRP_CD, CVR_GRP_NM
    tbl_recommendation    — 레거시 ML 추천결과 (고객번호, REC_RANK, REC_GDCD, REC_GDNM)
                            ※ Oracle M_CRM_REC_RLT_BIZ에서 적재, REC_RS1(기존 스크립트) 제외
                            ※ 신규 고객은 row 없음 → agent가 eligibility + RAG로 직접 추천
    tbl_change_log        — 임팩트 있는 변경 감지 기록 (고객번호, 변경항목, 변경일시)
                            ※ 임팩트 기준: 통화 진행/문자 발송/계약 체결
                            ※ M4에서 구현 (시간 여유 있을 때)

    공통 JOIN 키: CALL_ID (통화 단위), CTMNO (고객 단위)
    갱신 주기: 매일 cron (Oracle 마트는 새벽 배치, DuckDB는 D-1 데이터 참조)
```

### 대화형 에이전트 (Gradio UI)

```
상담사/본사 스태프 입력 (Gradio, FastAPI IP 미들웨어로 접근 제어)
    ↓
[Tab 1: 콜 전 준비] — 상담사 전용, 핵심 탭
    고객번호 입력
    → DuckDB: tbl_call_detail WHERE CTMNO = ? → 3분기 자동 결정
    │
    ├─ [신규 고객] tbl_call_detail row 없음
    │   → DuckDB: tbl_customer (인구통계, 유입 캠페인명) 조회
    │   → DuckDB: tbl_coverage (보장분석 대분류 담보금액) 조회
    │   → DuckDB: tbl_recommendation → ML 추천 상품 조회 (없으면 RAG로 대체)
    │   → Chroma: 캠페인명 필터 + 체결여부=Y → 유사 성공 콜 RAG
    │       └─ 캠페인 매칭 없으면: 필터 드롭 → 인구통계 기반 폴백 검색
    │   → gd_filter_func: 나이/성별 기반 가입 가능 여부 확인 (eligibility check)
    │   → Qwen3.6 → 첫 통화 스크립트 + 상품 추천 출력
    │
    ├─ [미연결 고객] row 있음 + 전부 결번/무응답
    │   → DuckDB: tbl_call_detail → 접촉 시도 횟수, 시도 시간대(TIMESTAMP) 조회
    │   → DuckDB: tbl_customer (인구통계) 조회
    │   → DuckDB: tbl_contract_history (가입 상품 수, 월 보험료, 최근 가입 시점)
    │   → DuckDB: tbl_new_coverage (3개월 내 신규 담보)
    │   → DuckDB: tbl_coverage, tbl_recommendation 조회
    │   → Chroma: 인구통계 기반 유사 성공 콜 RAG (해당 고객 녹취 없음)
    │   → gd_filter_func: eligibility check
    │   → Qwen3.6 → 신규 고객 스크립트 + 상품 추천 출력
    │       출력 순서: 계약 현황(미연결 시도 시간대 경고) → 보장 현황 → 스크립트
    │
    └─ [이력 고객] row 있음 + 실제 통화 1건 이상
        → DuckDB: tbl_call_detail (통화 TIMESTAMP 포함) → 시간대별 반응 분석
        → DuckDB: tbl_contract_history (가입 상품 수, 월 납입 보험료 합계, 최근 가입 시점)
        → DuckDB: tbl_new_coverage (3개월 이내 신규 가입 담보)
        → DuckDB: tbl_design_history 조회
        → DuckDB: tbl_coverage (현재 담보현황) 조회
        → DuckDB: tbl_recommendation → ML 추천 상품 조회
        → Chroma: 해당 고객 과거 통화 요약 RAG
        → Qwen3.6 → 재통화 맞춤 스크립트 + 상품 추천 출력
            출력 순서:
            ① 계약 현황 요약 (보장 현황 위에 표시)
               - 가입 상품 수, 월 납입 보험료, 최근 가입 시점
               - 3개월 내 신규 담보 (있으면 NEW 표시)
               - 추천 통화 시간 / 피해야 할 시간 (통화 패턴 기반 객관적 사실)
            ② 현재 보장 현황 (담보 gap)
            ③ 추천 상품 + 맞춤 스크립트
               (3월 통화 맥락 + 상품 설명서 PDF + 담보 gap 반영)

    ※ 레거시 연동: Gradio API로 상품 추천 결과(상품명/텍스트)를
      기존 레거시 상담사 UI에 주입 가능 (향후 확장)

[Tab 2: 영업지원 Agent] — 본사 스태프(기획자/운영자) 전용, 대화형 멀티턴
    단일 채팅 인터페이스, LangGraph가 의도를 파악해 세 가지 모드로 자동 라우팅

    ├─ [모드 A: 자유 질의] — 성과 조회, 정보 검색
    │   주요 용도:
    │     - 캠페인별 매출/체결율 조회 → DuckDB 집계 (자주 쓰는 지표는 템플릿 쿼리)
    │     - 신상품/내부 문서 정보 조회 → Chroma products RAG
    │   → Qwen3.6 → 질의 맞춤 응답 반환
    │   ※ 복잡한 집계 쿼리는 "AI 생성 결과, 반드시 확인" 경고 표시
    │
    ├─ [모드 B: 스크립트 생성] — TM 녹취 기반 봇/캠페인 스크립트 생성
    │   예시: "마케팅 동의봇 스크립트 만들어줘", "암보험 거절 극복 스크립트"
    │   → Chroma calls RAG: 체결여부/우호적여부 필터 → 유사 성공/실패 콜 패턴 추출
    │   → Chroma products RAG: 관련 상품 정보
    │   → Qwen3.6 → 봇/캠페인용 스크립트 반환
    │
    └─ [모드 C: 캠페인 고객 리스트 생성]
        Step 1. 운영자 입력: 과거 캠페인 목록 선택 OR 직접 설명
        Step 2. 과거 캠페인 성과 분석 먼저 표시
            → DuckDB: tbl_campaign_history → 유사 캠페인 체결 건수, 체결율, 세그먼트별 성과
            → "이 조건에서 과거 체결율이 가장 높았습니다" 인사이트 제공
        Step 3. AI 추천 조건 제안
            → 과거 성과 패턴 기반 → "이 조건으로 추출하면 동일 세그먼트 과거 체결율 X%"
            → tbl_campaign_score (외부 모델 점수) 높은 순으로 정렬
            → CM 채널: 갱신 가능성 높은 고객 제외
            → "리스트 받기" 확인 버튼
        Step 4. 결과 출력
            ① Excel 다운로드 (CTMNO만)
            ② 과거 동일 조건 세그먼트 체결율 (ML 예측 아님, 과거 실적 참고치)
            ③ 접근 전략 요약
```

## Gradio UI 설계 (확정)

- **탭 구성**: Tab1 콜 전 준비 (상담사) / Tab2 영업지원 Agent (본사 스태프) — 2탭
- **사용자**: 상담사 (Tab1 전용) + 본사 스태프/기획자/운영자 (Tab2 전용)
- **Tab2 UX**: 단일 채팅 인터페이스 — 라디오 버튼 없음, LangGraph가 의도 자동 라우팅
- **접근 제어**: FastAPI 미들웨어로 허용 IP 목록 검사 (설정 파일로 관리, 2차 방어선)
- **세션 구분 키**: IP 기반 (사내망 내부 IP, 동시 사용자 ~5명)
- **LLM**: 단일 Qwen3.6-27B — 멀티 LLM 불필요 (VRAM 40GB, 순차 사용)
- **레거시 연동**: Gradio API를 통해 레거시 상담사 UI에 추천 결과 주입 가능 (향후 확장)
- DuckDB 수동 갱신 버튼 + 마지막 갱신 시각 표시 필요

## Chroma 컬렉션 구조

| 컬렉션 | 임베딩 대상 | metadata 주요 필드 |
|--------|------------|-------------------|
| `calls` | 녹취 요약 | 마스킹 원문, CALL_ID, 고객번호, 체결여부, 통화시간, 우호적여부, 키워드(comma-separated), 캠페인명, **채널유형(CHANNEL_TYPE)**, 보장분석 대분류 담보금액 12개 |
| `products` | 상품/문서 마크다운 | 문서명, 카테고리, 페이지/슬라이드 번호 |

## Key Decisions (변경 시 재검토 필요)

- **Qwen3.6-27B Q4_K_M 선택**: ~16.8GB VRAM, KV캐시 여유 ~23GB. Q8_0(29GB)에서 변경 — Ollama 기동 실패 후 교체, 리소스 여유 확보
- **Ollama 선택 이유**: GGUF 직접 임포트 가능, 단일 바이너리, CUDA 자동 감지
- **faster-whisper large-v3**: 한국어 콜센터 녹취 정확도 최고, 배치라 속도보다 정확도 우선
- **Pipeline A 실행 시점**: 서비스 시작 전 1회 완료 후 서비스 가동 — Gradio UI와 동시 실행 없음, Qwen3.6 리소스 충돌 없음. 약 41~83시간 소요 예상 (5천 건 × 30~60초)
- **1건 = 1 chunk**: 평균 3분 = 500~700 토큰, 분할 불필요
- **개인정보 마스킹**: STT 직후 즉시 처리, 원문 보관 없음 — 1단계 Regex(전화번호/주민번호/계좌번호/카드번호), 2단계 Qwen3.6(이름/주소 등 비정형) — 마스킹+분석 통합 호출로 LLM 호출 최소화
- **Chroma 임베딩 전략**: 요약 텍스트를 임베딩, 마스킹된 원문은 metadata로 저장 — 검색 품질과 원문 활용 동시 확보
- **Chroma metadata 타입 제약**: Chroma는 metadata 값으로 scalar(string/int/float/bool)만 허용 — keywords는 list 불가, comma-separated string으로 저장
- **Chroma resume 로직**: collection 단위가 아닌 CALL_ID/문서명 단위로 get() 체크 후 skip — 중간 실패 시 재시작 가능
- **Chroma 선택 이유**: 로컬 파일 기반, 서버 불필요, langchain 네이티브 연동
- **Ollama 임베딩(nomic-embed-text)**: sentence-transformers 추가 불필요, 스택 단일화
- **RAG 방식**: fine-tuning 대신 RAG — 폐쇄망 데이터 추가/수정 용이, 환각 감소
- **RAG 프롬프트**: 직접 작성 (한국어 도메인 맞춤), LangChain Hub/LangSmith 사용 안 함
- **DuckDB 선택**: Oracle 집계를 인프로세스 OLAP으로 처리 — 에이전트 실행 시 Oracle 연결 불필요, 집계 속도 우수
- **DuckDB 구조**: 도메인별 테이블 10개 — Oracle은 OLTP 로그 원본, DuckDB가 분석용 스냅샷 (D-1 기준)
- **DuckDB 동시성**: 갱신 시 별도 파일(mart_new.db)에 쓴 후 atomic rename — TRUNCATE 중 에이전트 쿼리 블로킹 방지
- **DuckDB Tool 선택**: LangGraph Tool로 쿼리 등록, LLM이 tool description 보고 선택
- **DuckDB 자유 질의 정확도**: 단순 집계는 Qwen3.6 처리 가능, 복잡한 다중 JOIN은 오류 위험 — 자주 쓰는 지표는 사전 정의 템플릿 쿼리로 제공, 자유 질의 결과에는 "반드시 확인" 경고 표시
- **WAV ↔ DuckDB 매핑**: 파일명에서 CALL_ID 파싱 → tbl_call_detail 1-hop → CTMNO (Oracle 직접 조회 불필요)
- **Tab1 3분기 자동 분기**: tbl_call_detail row 없음 → 신규 / 전부 결번·무응답 → 미연결 / 실제 통화 1건 이상 → 이력. 상담사 수동 선택 불필요
- **통화이력 타임라인 표시**: 이력 고객에게 통화일시(TIMESTAMP) + 통화시간(초) 표시. STT 있으면 우호적여부 추가, STT 없으면 사실만 표시 (30초 이상 = "대화 진행됨"). 반응 좋음/나쁨 주관적 판단 없음 — 상담사가 직접 해석
- **통화 평가 탭 제거**: 상담사가 콜 후 별도 탭 조회 가능성 낮음 → 과거 통화 요약을 Tab1 2차 DB 플로우에 통합
- **Tab2 영업지원 Agent**: 단일 채팅 인터페이스, 모드A(자유 질의) + 모드B(스크립트 생성) + 모드C(캠페인 리스트 생성) 자동 라우팅
- **Tab2 의도 분류 오류 복구**: 분류 결과를 응답 첫 줄에 명시 + "다른 작업이라면 말씀해 주세요" 안내 → 오분류 즉시 수정 가능, 별도 UI 버튼 불필요
- **Tab2 스크립트 생성 (모드B)**: 본사 스태프가 봇/캠페인용 스크립트 제작 시 활용 — Chroma calls(TM 녹취 패턴) + products RAG → Qwen3.6 생성 (상담사용 개인화 스크립트인 Tab1과 구분)
- **캠페인 리스트 생성 (모드C)**: 운영자가 캠페인 방향만 제공 → 시스템이 유사 과거 캠페인 패턴으로 추출 조건 제안 → 확인/수정 후 DuckDB 조회 → Excel(CTMNO만) 다운로드
- **캠페인 리스트 출력 형식**: CTMNO만 포함한 Excel — 기존 콜링/문자 발송 시스템에 업로드하는 용도
- **예상 효율 산출 방식**: ML 예측 모델 아님 — 과거 유사 캠페인 실제 체결율 DuckDB 집계 기반 참고치 (정직한 방법)
- **CM 채널 마케팅 비용 절감**: 갱신 가능성 높은 고객을 리스트에서 제외 → 불필요 접촉 감소
- **유입경로 = 캠페인명**: tbl_campaign_history에서 캠페인명 조회 → Chroma 메타데이터 필터 키로 사용
- **신규 캠페인 폴백**: 캠페인명 매칭 없으면 필터 드롭 → 전체 성공 콜 + 인구통계 기반 유사도 검색
- **레거시 추천 시스템 유지**: Oracle M_CRM_REC_RLT_BIZ → tbl_recommendation 적재 (CTMNO/REC_RANK/REC_GDCD/REC_GDNM만, REC_RS1 제외)
- **신규 고객 추천**: tbl_recommendation row 없으면 gd_filter_func(eligibility) + 유입경로 + Chroma RAG → agent가 직접 판단
- **Tab1 콜 전략 설계**: go/no-go 판단이 아님. 시간 경과 + 이전 터치 이력 → "지금 이 각도가 유효한가" 해석. 2차 DB는 동일 상담사 재연락 아님(캠페인 변경/POM 유입 구조) — 기본은 새 고객처럼 접근, 이전 이력은 전략 힌트
- **tbl_new_coverage 추가**: 3개월 이내 신규 가입 담보 테이블 — Tab1 계약 현황 섹션 + 스크립트에서 "최근 가입하신 [담보명]과 연계하여" 활용. Oracle INS_CR_CVR 계열에서 CVR_START_DT 기준 필터
- **tbl_campaign_score 추가**: 외부에서 만든 캠페인 추천도 모델 결과 적재 (레거시 상품추천시스템과 동일 방식) — CTMNO + SCORE + CAMPAIGN_TYPE. Tab2 모드C 고객 정렬에 활용
- **Tab1 출력 순서 확정**: 계약 현황(가입 상품 수, 월 납입 보험료, 최근 가입 시점, 3개월 내 신규 담보, 통화 추천/피해야 할 시간) → 현재 보장 현황 → 추천 상품 → 스크립트
- **Tab2 캠페인 시뮬레이터 UX**: 과거 캠페인 성과 분석 먼저 표시 → 체결 패턴 인사이트 → AI 추천 조건 제안 → 리스트 받기 확인. "예상 체결율"이 아닌 "과거 동일 조건 세그먼트 체결율"로 명시 (ML 예측 아님)
- **Pipeline B MVP 복귀**: 상품 설명서 PDF가 Tab1 스크립트에 필수 — 비갱신형/납입기간/특약 등 상품 특징을 스크립트에 반영하려면 products RAG 필요. 이월 취소
- **gd_filter_func 재사용**: 기존 `GDREC_GD_filter.py` 코드 그대로 `utils/eligibility.py`에 포팅 — L01/L04/L03/SS는 나이+성별 분기, 유병자는 병력 4개 컬럼(입원청구/입원고지/중대질환고지/중대질환청구) min값 기반 분기
- **병력 컬럼 DuckDB 적재**: 유병자 판단용 4개 컬럼을 tbl_customer에 포함 — 컴플라이언스 승인 완료, GDREC_ORIGIN_MAIN_FIN_PRED에서 가져옴
- **통화이력 30초 기준**: STT 없는 고객의 통화이력 표시에서 CALL_DURATION 30초 이상이면 "대화 진행됨" 표시, 미만은 시간만 표시 — 주관적 판단 없이 사실만 기재
- **콜드스타트 전략**: Tab1 1차 DB 플로우에 통합 — 별도 탭 없음
- **모의 상담 제거**: 시간 대비 효용 낮음, 다음 버전으로 이월
- **Oracle 쿼리 분리**: 상품추천쿼리.txt는 레거시 학습 데이터 생성용으로 보존, DuckDB 적재용 SELECT 쿼리는 db/oracle_queries.py에 별도 작성
- **담보 구조 분리**: tbl_coverage(대분류 wide 12컬럼, 스크립트용) + tbl_coverage_detail(담보코드 long, LIKE 검색용) + tbl_cvr_group_map(커스텀 그룹명 매핑, LLM 초안+검수)
- **tbl_customer Oracle 소스**: 신규 마트 필요 — CUS_CTM(전체 30만) LEFT JOIN GDREC_ORIGIN_MAIN_FIN_PRED(기존 계약 고객), 담보금액/계약/설계 컬럼 제외
- **개인정보**: 청구/보상이력 등 민감 데이터 DuckDB 제외, 컴플라이언스 승인 범위 내 컬럼만 적재
- **접근 제어**: FastAPI 미들웨어 IP 필터 (허용 목록 설정 파일) + 정보보호 파트 네트워크 레벨 2중 제어
- **온디맨드 생성**: 30만 건 사전 생성 아님 — 상담사 요청 시 단건 생성. DuckDB 조회(<1초) + LLM 스트리밍(10~30초). 사전 생성 불필요
- **Tab1 출력 2단계 분리**: ①DuckDB 결과(계약현황/보장현황) 즉시 표시 → ②LLM 스크립트 스트리밍. 상담사가 ①읽는 동안 ②생성 완료 — 체감 대기 없음
- **Tab1 스트리밍**: Gradio gr.Markdown(즉시) + gr.Textbox 스트리밍 조합. langchain-ollama 네이티브 스트리밍 지원
- **WAV 파일명 확정**: CALL_ID.wav 형식 — Path.stem = CALL_ID 그대로 사용
- **tbl_coverage Oracle 소스**: GDREC_ORIGIN_MAIN_FIN_PRED 최종 마트, 단순 SELECT. 9단계 중간 계산 불필요
- **RESULT_CD ETL 번역**: Oracle 원본 코드 저장 안 함 — oracle_queries.py CASE WHEN으로 "미연결"/"연결성공" 번역 적재. 애플리케이션 코드에서 Oracle 코드 상수 불필요
- **CHANNEL_TYPE 추가**: tbl_call_detail + Chroma calls 메타데이터에 CHANNEL_TYPE 포함 — RAG 필터 기준 (채널×캠페인 조합이 다양해 채널 필터 필수)
- **Oracle 테이블명 _DS_ 패턴**: 기존 테이블명에 _DS_ 삽입. oracle_queries.py 쿼리는 2026-06-01 사용자 제공 예정
- **Pipeline A 5000건 일괄**: 캠페인×채널 조합이 수십~수백개라 수동 선별 불가 — 5,000건 전체 일괄 인덱싱. Day 3 시작, 41~83시간 소요. 개발 기간에는 Chroma 없이 DuckDB+products RAG만으로 Tab1 개발, Pipeline A 완료 시 calls RAG 자동 활성화
- **개발 환경 2컨테이너**: Jupyter 컨테이너(Oracle 쿼리 검증 전용) + LLM 컨테이너(VS Code, DuckDB 생성/운영/Gradio 앱). Shared volume 불가 — DuckDB는 LLM 컨테이너에서만 관리. Jupyter에서 검증된 쿼리 → oracle_queries.py 복사 → LLM 컨테이너 터미널 실행
- **비전 LLM**: 인덱싱 시에만 사용 (Qwen3.6 언로드 후 순차), 쿼리 타임에는 불필요 — 모델 미정
- **문서 포맷**: DOCX/PPTX/PDF만 지원 (HWP 없음)
- **마트 갱신**: 매일 cron 자동 실행
- **script_angle 3분기**: 체결이력 있음 → `complement`(담보 gap 기반 보완), 설계이력만 있음 → `followup`(설계 건 팔로업), 이력 없음 → `new_product`(신상품 공략). Qwen3.6 프롬프트에 명시 전달. 시간 무관 — 연결성공+체결없으면 각도 유지
- **이미 가입 상품 GDCD 필터 불필요**: 담보 gap(tbl_coverage)이 이미 "무엇이 부족한지" 나타냄 → 중복 가입 방향 자연 차단
- **gd_filter_func 적용 범위**: 신규 고객 한정 아님 — ML 추천 결과가 있어도 eligibility 체크 통과해야 추천. tbl_ds_recommendation + gd_filter_func 항상 조합
- **tbl_ds_product_master 추가**: GDCD → GD_TYPE → GDNM_CLEAN 매핑 테이블. Oracle 소스: GDREC_TMGD_LIST와 동일 마스터(현재 판매 TM 상품만). gd_filter_func 반환 상품명 → GDCD 역매핑에 사용
- **CTM_SEX Oracle 코드 원본 적재**: `'1.M'`/`'2.F'` 변환 없이 DuckDB에 그대로 적재. eligibility.py에서도 동일 코드 사용
- **Chroma embedded_text 포맷 확정**: `f"[고객: {age}세 {sex}, {campaign_nm}] {summary}"` — Pipeline A에서 tbl_customer(CTM_AGE, CTM_SEX) 추가 조회 후 구성. 신규/미연결 RAG 쿼리와 동일 시맨틱 공간
- **Chroma RAG 케이스별 전략**: 이력 고객 → `collection.get(where={"CTMNO": ctmno})` 직접 조회(유사도 검색 아님). 신규/미연결 → `collection.query(query_texts=[인구통계+담보gap 텍스트])`. Chroma 결과 없어도 DuckDB+products RAG로 정상 생성
- **LangGraph 그래프 분리**: Tab1 = 별도 그래프, checkpoint 없음(매 요청 fresh). Tab2 = 별도 그래프, checkpoint-sqlite(IP 기반 멀티턴 세션). Tab1↔Tab2 상태 공유 없음
- **Tab2 모드C 확인 UX**: 단일 채팅 인터페이스 유지 — 버튼 없음. 시스템이 텍스트로 `"이 조건으로 추출할까요? (네/수정할게요)"` 제시, 사용자 텍스트로 확인
- **Tab2 모드C SQL 생성**: LLM이 SQL 직접 생성 안 함. 자연어 → 구조화 conditions dict 변환 → `build_campaign_query(conditions)` 템플릿 함수로 쿼리 생성
- **Pipeline C 장애 복구**: 시작 시 mart_new.db 존재하면 무조건 삭제 후 재시작. 부분 복구 없음(Oracle 전체 재적재)
- **IP 기반 세션 충돌 리스크 인지**: 사내망 고정 IP 보장 없음 → NAT 충돌 시 Tab2 세션 섞일 수 있음. 동시 사용자 ~5명 + 실사용 패턴상 충돌 빈도 낮아 별도 처리 없이 감수

## 개발 타임라인 (마감: 2026-06-09, 10일)

### MVP 범위 (10일 내 완성)
- Tab1 콜 전 준비 전체 (상담사 핵심)
- Tab2 모드C 캠페인 리스트 생성 (임원 데모 핵심)
- Gradio 2탭 기본 UI

### 이월 (다음 버전)
- Tab2 모드A 자유 질의 → 템플릿 쿼리 몇 개로 우선 대체
- tbl_coverage_detail / tbl_cvr_group_map
- tbl_change_log

### 10일 플랜

| 일차 | 날짜 | 작업 |
|------|------|------|
| Day 1 | 5/31 | config/settings.py + db/schema.sql + db/manager.py |
| Day 2 | 6/1 | db/oracle_queries.py + pipelines/pipeline_c_duckdb.py + DuckDB 적재 실행 |
| Day 3 | 6/2 | pipelines/pipeline_a_stt.py + pipelines/pipeline_b_docs.py + utils/masking.py + utils/eligibility.py + Pipeline A/B 백그라운드 시작 |
| Day 4 | 6/3 | agent/state.py + agent/tools/duckdb_tools.py + agent/tools/chroma_tools.py |
| Day 5 | 6/4 | agent/nodes/router.py (3분기) + Tab1 신규/미연결 플로우 |
| Day 6 | 6/5 | Tab1 이력 플로우 (Chroma RAG + 통화이력 타임라인) + agent/graph.py Tab1 완성 |
| Day 7 | 6/6 | Tab2 의도 라우터 + 모드C 캠페인 리스트 생성 4단계 + Excel 출력 |
| Day 8 | 6/7 | ui/app.py (2탭) + ui/middleware.py + Tab1 E2E 연동 |
| Day 9 | 6/8 | Tab2 채팅 UI + E2E 연동 + DuckDB 갱신 버튼 + 버그 수정 |
| Day 10 | 6/9 | 폐쇄망 배포 패키지 점검 + 시나리오 E2E 테스트 |

### 리스크
- **Pipeline A 처리 시간**: Day 3 시작 시 41~83시간 소요. 개발은 Chroma 없이 진행, 완료 후 RAG 자동 활성화
- **Oracle 테이블명**: _DS_ 패턴 적용, 쿼리는 6/1 사용자 제공. Day 2 오전 수령 후 바로 pipeline_c 작성
