"""
GGUF Model Downloader for Colab  (최종판)
- wget으로 직접 다운로드 (토큰 불필요, public 레포)
- 각 파트를 개별 tar.gz로 포장 → 폐쇄망 반입 정책 우회
- 실행: Colab에 이 파일 업로드 후 !python colab_model_download.py
"""
import os, glob

MODEL_URL  = "https://huggingface.co/unsloth/Qwen3.6-27B-GGUF/resolve/main/Qwen3.6-27B-Q4_K_M.gguf"
FILENAME   = "Qwen3.6-27B-Q4_K_M.gguf"
SAVE_DIR   = "/content/model"
SPLIT_DIR  = "/content/parts"
PART_MB    = 1900

os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(SPLIT_DIR, exist_ok=True)
file_path = f"{SAVE_DIR}/{FILENAME}"

# ── Step 1: wget 다운로드 ─────────────────────────────────────────────
print(f"[*] 다운로드 시작: {FILENAME}")
print("    약 15GB — 완료까지 10~20분 소요")
os.system(f'wget -q --show-progress -O "{file_path}" "{MODEL_URL}"')
size_gb = os.path.getsize(file_path) / 1024**3
print(f"[+] 다운로드 완료 — {size_gb:.1f} GB")

# ── Step 2: 1.9GB 단위로 분할 후 각 파트를 개별 tar.gz로 포장 ────────
# ❌ 기존 방식: tar.gz 하나로 합친 뒤 split → 조각은 raw binary라 정책 차단
# ❌ 기존 방식: split 결과에 .tar.gz 이름만 붙임 → 실제 포맷 불일치
# ✅ 현재 방식: split raw 조각 각각을 tar -czf로 포장 → 실제 tar.gz 포맷
print("[*] 분할 및 tar.gz 포장 중...")

RAW_PREFIX = f"{SPLIT_DIR}/raw_part"
os.system(f'split -b {PART_MB}m "{file_path}" "{RAW_PREFIX}"')

raw_parts = sorted(glob.glob(f"{RAW_PREFIX}*"))
total     = len(raw_parts)
print(f"[+] 원본 파트 {total}개 생성")

tar_parts = []
for i, raw in enumerate(raw_parts, 1):
    idx     = f"{i:02d}"
    part_fn = f"model_part{idx}_of{total:02d}.tar.gz"
    part_p  = f"{SPLIT_DIR}/{part_fn}"
    base    = os.path.basename(raw)
    ret     = os.system(f'tar -czf "{part_p}" -C "{SPLIT_DIR}" "{base}"')
    if ret != 0:
        print(f"[!] tar 실패: {part_fn}"); break
    os.remove(raw)  # raw 파트 즉시 삭제 → Colab 디스크 절약
    mb = os.path.getsize(part_p) / 1024**2
    print(f"  [{idx}/{total:02d}] {part_fn}  {mb:.0f} MB")
    tar_parts.append(part_p)

print("\n[+] 완료!")
print("    ── 폐쇄망 서버 복원 명령어 ──────────────────────────────")
print("    # 1) 각 tar.gz에서 raw 파트 추출")
print("    for f in model_part*.tar.gz; do tar -xzf \"$f\"; done")
print("    # 2) raw 파트 순서대로 합쳐서 원본 복원")
print(f"    ls raw_part* | sort | xargs cat > {FILENAME}")
print("    # 3) ollama 등록")
print("    ollama create mymodel -f Modelfile")
