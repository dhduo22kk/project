# Project: AI Consultation Agent

## Purpose
콜센터 고객 상담 WAV 녹취 파일(소수, ~5천 건)을 STT 처리 후 벡터DB에 인덱싱하고,
전체 고객(~30만 명)의 Oracle 데이터를 DuckDB로 적재하여,
상담사가 콜 전 고객 맞춤 스크립트/상품 추천을 조회하고,
기획자가 캠페인 성과 분석 및 스크립트를 생성하는 대화형 에이전트.

### 핵심 사용 목적
1. **콜 전 준비 (상담사)** — 고객 조회 → 1차/2차 DB 자동 분기 → 맞춤 스크립트 + 상품 추천
2. **통화 평가 (상담사/기획자)** — 콜 후 CALL_ID 기반 분석, 2차 통화 제안 생성
3. **캠페인 성과 분석 (기획자)** — DuckDB 집계 기반 자유 질의
4. **스크립트 생성 / 모의 상담 연습 (상담사)** — 상황별 스크립트 생성, LLM 고객 역할 모의 대화

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
                키워드, 캠페인명, 보장분석 대분류 담보금액 12개
    ※ resume: Chroma collection ID 체크 → 이미 존재하면 skip (별도 추적 파일 불필요)
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
```

### 배치 파이프라인 C: DuckDB 마트 갱신 (매일 cron 자동 실행)

```
Oracle DB (cx_Oracle) — 이력 로그 테이블 원본
    ↓
도메인별 추출 쿼리 실행 (사용자 사전 작성)
    ↓
DuckDB 도메인 테이블로 저장 (로컬, 인프로세스)

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
상담사/기획자 입력 (Gradio, FastAPI IP 미들웨어로 접근 제어)
    ↓
[Tab 1: 통화 평가] — 콜 후 사용
    CALL_ID 입력
    → DuckDB Tool: tbl_call_detail 조회
    → Chroma: 해당 콜 STT 원문/요약/키워드 조회
    → DuckDB Tool: tbl_customer, tbl_campaign_history 조회
    → Qwen3.6 → 출력:
        ① 상담 분위기 및 요약
        ② 간단한 평가
        ③ 2차 통화 제안 (고객이 한 말 + 고객 속성 기반)

[Tab 2: 콜 전 준비] — 콜 전 사용 (핵심 탭)
    고객번호 입력
    → DuckDB: tbl_call_detail WHERE CTMNO = ? → COUNT로 1차/2차 자동 분기
              (결번/무응답 포함 1건이라도 있으면 2차)
    │
    ├─ [1차 DB] tbl_call_detail row 없음 (첫 통화)
    │   → DuckDB: tbl_customer (인구통계, 유입 캠페인명) 조회
    │   → DuckDB: tbl_coverage (보장분석 대분류 담보금액) 조회
    │   → DuckDB: tbl_recommendation → ML 추천 상품 조회 (없으면 RAG로 대체)
    │   → Chroma: 캠페인명 필터 + 체결여부=Y → 유사 성공 콜 RAG
    │       └─ 캠페인 매칭 없으면: 필터 드롭 → 인구통계 기반 폴백 검색
    │   → gd_filter_func: 나이/성별 기반 가입 가능 여부 확인 (eligibility check)
    │   → Qwen3.6 → 첫 통화 스크립트 + 상품 추천 출력
    │       (ML 추천 카테고리 + 담보 gap 분석 + 유사 성공 사례 기반)
    │
    └─ [2차 DB] tbl_call_detail row 1건 이상 (재통화)
        → DuckDB: tbl_call_detail, tbl_contract_history, tbl_design_history 조회
        → DuckDB: tbl_coverage (현재 담보현황) 조회
        → DuckDB: tbl_recommendation → ML 추천 상품 조회
        → Chroma: 해당 고객 과거 통화 요약 RAG
        → Qwen3.6 → 재통화 맞춤 스크립트 + 상품 추천 출력
            (담보 gap 분석 + 과거 통화 맥락 + ML 추천 카테고리 기반)

[Tab 3: 스크립트 생성 / 분석 / 모의 상담] — 자유 활용
    Radio 버튼으로 모드 선택 → LangGraph 라우팅 (LLM 의도 분류 불필요)
    │
    ├─ [캠페인 분석] 기획자용: 캠페인 성과, 집계 자유 질의
    │   → DuckDB Tool → 집계 결과 반환
    │
    ├─ [스크립트 생성] 상담사용: 상황별/거절 극복 스크립트 생성
    │   → Chroma RAG (체결여부=N + 우호적=True → 아깝게 실패한 콜 분석)
    │   → DuckDB: tbl_coverage 유사 고객 동적 집계 (고정 통계 테이블 미사용)
    │   → Qwen3.6 → 거절 극복 플레이북 + 스크립트 반환
    │
    └─ [모의 상담] 상담사용: LLM이 고객 역할로 실전 연습
        → Tab 2 컨텍스트 연계 또는 조건 직접 입력
        → Chroma: 유사 고객 페르소나 구성
        → Qwen3.6: 고객 역할 수행, 멀티턴 대화
```

## Gradio UI 설계 (확정)

- **탭 구성**: Tab1 통화평가 / Tab2 콜 전 준비 / Tab3 스크립트+분석+모의상담 (3탭)
- **사용자**: 상담사 (Tab2 주사용) + 기획자 (Tab3 주사용), Tab1은 공용
- **접근 제어**: FastAPI 미들웨어로 허용 IP 목록 검사 (설정 파일로 관리, 2차 방어선)
- **세션 구분 키**: IP 기반 (사내망 내부 IP, 동시 사용자 ~5명)
- **LLM**: 단일 Qwen3.6-27B — 멀티 LLM 불필요 (VRAM 40GB, 순차 사용)
- **Tab 3 모드 선택**: Radio 버튼 [캠페인 분석 / 스크립트 생성 / 모의 상담] — LLM 의도 분류 없음
- DuckDB 수동 갱신 버튼 + 마지막 갱신 시각 표시 필요

## Chroma 컬렉션 구조

| 컬렉션 | 임베딩 대상 | metadata 주요 필드 |
|--------|------------|-------------------|
| `calls` | 녹취 요약 | 마스킹 원문, CALL_ID, 고객번호, 체결여부, 통화시간, 우호적여부, 키워드(5개), 캠페인명, 보장분석 대분류 담보금액 12개 |
| `products` | 상품/문서 마크다운 | 문서명, 카테고리, 페이지/슬라이드 번호 |

## Key Decisions (변경 시 재검토 필요)

- **Qwen3.6-27B Q4_K_M 선택**: ~16.8GB VRAM, KV캐시 여유 ~23GB. Q8_0(29GB)에서 변경 — Ollama 기동 실패 후 교체, 리소스 여유 확보
- **Ollama 선택 이유**: GGUF 직접 임포트 가능, 단일 바이너리, CUDA 자동 감지
- **faster-whisper large-v3**: 한국어 콜센터 녹취 정확도 최고, 배치라 속도보다 정확도 우선
- **1건 = 1 chunk**: 평균 3분 = 500~700 토큰, 분할 불필요
- **개인정보 마스킹**: STT 직후 즉시 처리, 원문 보관 없음 — 1단계 Regex(전화번호/주민번호/계좌번호/카드번호), 2단계 Qwen3.6(이름/주소 등 비정형) — 마스킹+분석 통합 호출로 LLM 호출 최소화
- **Chroma 임베딩 전략**: 요약 텍스트를 임베딩, 마스킹된 원문은 metadata로 저장 — 검색 품질과 원문 활용 동시 확보
- **Chroma 선택 이유**: 로컬 파일 기반, 서버 불필요, langchain 네이티브 연동
- **Ollama 임베딩(nomic-embed-text)**: sentence-transformers 추가 불필요, 스택 단일화
- **RAG 방식**: fine-tuning 대신 RAG — 폐쇄망 데이터 추가/수정 용이, 환각 감소
- **RAG 프롬프트**: 직접 작성 (한국어 도메인 맞춤), LangChain Hub/LangSmith 사용 안 함
- **DuckDB 선택**: Oracle 집계를 인프로세스 OLAP으로 처리 — 에이전트 실행 시 Oracle 연결 불필요, 집계 속도 우수
- **DuckDB 구조**: 도메인별 테이블 10개 — Oracle은 OLTP 로그 원본, DuckDB가 분석용 스냅샷 (D-1 기준)
- **DuckDB Tool 선택**: LangGraph Tool로 쿼리 등록, LLM이 tool description 보고 선택 — RAG 불필요
- **WAV ↔ DuckDB 매핑**: 파일명에서 CALL_ID 파싱 → tbl_call_detail 1-hop → CTMNO (Oracle 직접 조회 불필요)
- **1차/2차 DB 자동 분기**: tbl_call_detail row 존재 여부만 확인 — 결번/무응답 포함 1건이라도 있으면 무조건 2차, 상담사 수동 선택 불필요
- **유입경로 = 캠페인명**: tbl_campaign_history에서 캠페인명 조회 → Chroma 메타데이터 필터 키로 사용
- **tbl_assignment 폐기**: 배정이력을 tbl_campaign_history에 통합 — 별도 테이블 불필요
- **신규 캠페인 폴백**: 캠페인명 매칭 없으면 필터 드롭 → 전체 성공 콜 + 인구통계 기반 유사도 검색
- **레거시 추천 시스템 유지**: Oracle M_CRM_REC_RLT_BIZ → tbl_recommendation 적재 (CTMNO/REC_RANK/REC_GDCD/REC_GDNM만, REC_RS1 제외)
- **신규 고객 추천**: tbl_recommendation row 없으면 gd_filter_func(eligibility) + 유입경로 + Chroma RAG → agent가 직접 판단
- **스크립트 생성 전략**: 고정 통계 테이블(M_BIZ_RECT_GDINFO_*) 미사용 → tbl_coverage 동적 집계 + Chroma RAG로 유사 고객 기반 맥락 생성
- **LLM 고도화 방향**: Qwen3.6을 단순 포맷 변환이 아닌 추론·판단에 활용. Tab1=상담원 코칭(놓친 포인트+다음 콜 전략), Tab2=이전 이력 기반 접근 전략, Tab3=프로필 기반 저항 페르소나
- **Tab2 콜 전략 설계**: go/no-go 판단이 아님. 시간 경과 + 이전 터치 이력 → "지금 이 각도가 유효한가" 해석. 2차 DB는 동일 상담사 재연락 아님(캠페인 변경/POM 유입 구조) — 기본은 새 고객처럼 접근, 이전 이력은 전략 힌트
- **Oracle 쿼리 분리**: 상품추천쿼리.txt는 레거시 학습 데이터 생성용으로 보존, DuckDB 적재용 SELECT 쿼리는 db/oracle_queries.py에 별도 작성
- **담보 구조 분리**: tbl_coverage(대분류 wide 12컬럼, 스크립트용) + tbl_coverage_detail(담보코드 long, LIKE 검색용) + tbl_cvr_group_map(커스텀 그룹명 매핑, LLM 초안+검수)
- **tbl_customer Oracle 소스**: 신규 마트 필요 — CUS_CTM(전체 30만) LEFT JOIN GDREC_ORIGIN_MAIN_FIN_PRED(기존 계약 고객), 담보금액/계약/설계 컬럼 제외
- **거절 극복 플레이북**: Tab3 스크립트 모드에서 Chroma 필터(체결여부=N, 긍부정=긍정) → 실패 원인 분석 + 대응 논리 생성
- **모의 상담 모드**: Tab3에서 LLM이 고객 역할, Chroma 유사 케이스로 페르소나 구성, Tab2 컨텍스트 연계 가능
- **콜드스타트 전략**: Tab2 1차 DB 플로우에 통합 — 별도 탭 없음
- **개인정보**: 청구/보상이력 등 민감 데이터 DuckDB 제외, 컴플라이언스 승인 범위 내 컬럼만 적재
- **접근 제어**: FastAPI 미들웨어 IP 필터 (허용 목록 설정 파일) + 정보보호 파트 네트워크 레벨 2중 제어
- **배치 스크립트 생성**: 수백~수천 건 고객ID 목록 입력 → 에이전트 루프 실행 → 결과 DuckDB 저장 (백그라운드, 100건≈50분/500건≈4시간)
- **변경 사항 기억**: tbl_change_log로 임팩트 있는 데이터 변경 추적 → 추천/스크립트 생성 시 컨텍스트 반영, 임팩트 기준은 DuckDB 구축 후 확정 (잠정: 통화 진행/문자 발송/계약 체결)
- **온디맨드 생성**: 30만 건 사전 생성 아님 — 상담사 요청 시 단건 생성 (~30초~1분), 배치는 별도 요청 시 실행
- **개발 환경**: GitHub Codespaces 유료 확인으로 사용 불가(2026-05-28). 대체 환경 미확정. Colab Pro GPU 런타임에서 실행, Google Drive에 데이터 저장
- **사용자**: 상담사 (Tab2 콜 전 준비 주사용) + 기획자 (Tab3 분석 주사용), 실시간 상담 보조 도구로 목적 전환
- **비전 LLM**: 인덱싱 시에만 사용 (Qwen3.6 언로드 후 순차), 쿼리 타임에는 불필요 — 모델 미정
- **문서 포맷**: DOCX/PPTX/PDF만 지원 (HWP 없음)
- **마트 갱신**: 매일 cron 자동 실행

## 개발 타임라인 (마감: 2026-06-09)

### M1 — 데이터 레이어 (05/27 ~ 05/30, 4일)
- [ ] DuckDB 스키마 정의 + 파이프라인 C (Oracle → DuckDB 갱신 스크립트)
- [ ] STT 배치 파이프라인 A (WAV → faster-whisper → Chroma `calls`)
- [ ] 문서 인덱싱 파이프라인 B (DOCX/PPTX/PDF → Chroma `products`)
- [ ] 파이프라인 resume 로직 (처리 완료 파일 skip)

### M2 — 에이전트 코어 (05/31 ~ 06/04, 5일)
- [ ] LangGraph State 구조 + 멀티턴 히스토리
- [ ] DuckDB Tools 등록 (테이블별 tool description)
- [ ] Chroma RAG Tool (calls / products 컬렉션)
- [ ] 1차/2차 DB 자동 분기 로직 (tbl_call_detail row 존재 여부)
- [ ] Tab 3 Radio 버튼 라우터 (캠페인 분석 / 스크립트 생성 / 모의 상담)

### M3 — Gradio UI + 통합 (06/05 ~ 06/07, 3일)
- [ ] Gradio 3탭 UI (Tab1 통화평가 / Tab2 콜 전 준비 / Tab3 자유활용)
- [ ] FastAPI IP 미들웨어 (허용 IP 설정 파일)
- [ ] Tab2 전체 플로우 E2E 연동 (핵심 탭)
- [ ] DuckDB 수동 갱신 버튼 + 마지막 갱신 시각 표시

### M4 — 마무리 + 배포 (06/08 ~ 06/09, 2일)
- [ ] 전체 E2E 테스트 (Tab1/2/3 시나리오별)
- [ ] 폐쇄망 배포 패키지 최종 점검 (번들 버전 정합성)
- [ ] tbl_change_log 구현 (시간 여유 있을 때만)

### 우선순위 원칙
- **Tab2 콜 전 준비** — 핵심, M3에서 가장 먼저 완성
- **tbl_change_log** — DuckDB 구축 후 기준 확정, M4로 미룸
- **비전 LLM / 모의 상담** — 시간 부족 시 다음 버전으로 이월
- **배치 스크립트 생성** — 핵심 기능 완성 후 여유 있을 때 추가
