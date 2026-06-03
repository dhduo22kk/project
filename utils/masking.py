"""
개인정보 마스킹 1단계 — Regex 기반 구조화 PII 치환

처리 순서 (중요: 카드번호 → 주민번호 → 전화번호 → 계좌번호)
  카드번호를 가장 먼저 처리해야 숫자 패턴 겹침 방지

2단계(이름/주소 등 비정형)는 pipeline_a_stt.py의 Qwen3.6 통합 호출에서 처리.
"""
import re

# 카드번호: XXXX-XXXX-XXXX-XXXX 또는 띄어쓰기 구분
_CARD = re.compile(
    r'(?<!\d)\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{4}(?!\d)'
)

# 주민등록번호: XXXXXX-XXXXXXX (뒷자리 첫 자리 1~4)
_JUMIN = re.compile(
    r'(?<!\d)\d{6}[\s\-]?[1-4]\d{6}(?!\d)'
)

# 전화번호: 010-XXXX-XXXX, 02-XXXX-XXXX, 지역번호 포함
_PHONE = re.compile(
    r'(?<!\d)'
    r'(?:0(?:10|1[1-9]|2|[3-6][1-5]|70|80|9[0-9]))'
    r'[\s\-]?\d{3,4}[\s\-]?\d{4}'
    r'(?!\d)'
)

# 계좌번호: 숫자 10~16자리 (하이픈/공백 포함), 전화번호 처리 후 적용
_ACCOUNT = re.compile(
    r'(?<!\d)\d{3,6}[\s\-]\d{2,6}[\s\-]\d{2,6}(?!\d)'
)


def mask_pii_regex(text: str) -> str:
    """STT 원문에 Regex 1단계 마스킹 적용. Pipeline A에서 STT 직후 호출."""
    text = _CARD.sub('[카드번호]', text)
    text = _JUMIN.sub('[주민번호]', text)
    text = _PHONE.sub('[전화번호]', text)
    text = _ACCOUNT.sub('[계좌번호]', text)
    return text
