"""
AI Bundle Downloader for Colab
- 패키지 다운로드 + server_env.txt 기준 중복 제거
- Ollama tar.zst → tar.gz 재압축 (폐쇄망 서버에 zstd 불필요)
- 실행: Colab에 이 파일과 server_env.txt 업로드 후 !python colab_bundle_download.py
"""
import os
import glob
from google.colab import files

SERVER_ENV = "/content/server_env.txt"
PKG_DIR    = "/content/packages"
OUTPUT     = "/content/ai_bundle.tar.gz"
PART_DIR   = "/content"
PART_SIZE  = "1900m"
MAX_BYTES  = 1.9 * 1024 ** 3

PACKAGES = [
    # STT / LLM
    "faster-whisper",
    "ctranslate2",
    # LangChain / Agent (langsmith 제외 — 폐쇄망 HTTP 통신 불가)
    # langchain-community 제외 — aiohttp 충돌, 우리 스택에서 불필요
    "langchain-core",
    "langchain",
    "langchain-ollama",
    "langchain-chroma",
    "langgraph",
    "langgraph-checkpoint-sqlite",
    "ollama",
    # 벡터DB
    "chromadb",
    # 분석DB
    "duckdb",
    # 문서 파싱
    "pymupdf4llm",
    "mammoth",
    "python-pptx",
    "python-docx",
    # UI
    "gradio",
]

INSTALL_SH = """\
#!/bin/bash
set -e
BUNDLE="$(cd "$(dirname "$0")" && pwd)"
echo "[*] Installing Python packages..."
pip3 install --no-index --find-links="$BUNDLE/packages" \\
    faster-whisper ctranslate2 \\
    langchain-core langchain langchain-ollama langchain-chroma \\
    langgraph langgraph-checkpoint-sqlite ollama \\
    chromadb duckdb \\
    pymupdf4llm mammoth python-pptx python-docx \\
    gradio
echo "[*] Installing Ollama..."
sudo tar -xzf "$BUNDLE/packages/ollama-linux-amd64.tar.gz" -C /usr/local/
sudo chmod +x /usr/local/bin/ollama
echo "[+] Ollama 버전: $(/usr/local/bin/ollama --version 2>/dev/null || echo '확인 불가')"
echo "[+] Done!"
echo "    ollama serve 로 서버 시작"
echo "    ollama create mymodel -f /path/to/Modelfile 로 모델 로드"
"""

# ── Step 1: server_env.txt 파싱 ───────────────────────────────────────
server_pkgs = {}
if os.path.exists(SERVER_ENV):
    with open(SERVER_ENV) as f:
        for line in f:
            if "==" in line:
                name, ver = line.strip().split("==", 1)
                server_pkgs[name.lower().replace("-", "_")] = ver
    print(f"[+] 서버 설치 패키지 {len(server_pkgs)}개 로드됨")
else:
    print("[!] server_env.txt 없음 — 전체 의존성 다운로드")

# ── Step 2: 패키지 다운로드 (버전 핀 없음 = 항상 최신) ───────────────
os.makedirs(PKG_DIR, exist_ok=True)
pkg_str = " ".join(PACKAGES)
ret = os.system(
    f"pip download {pkg_str} "
    f"--dest {PKG_DIR} "
    f"--platform manylinux_2_17_x86_64 "
    f"--python-version 310 "
    f"--implementation cp "
    f"--abi cp310 "
    f"--only-binary :all:"
)
if ret != 0:
    print("[!] 일부 패키지 다운로드 실패 — 위 오류 메시지 확인")

# ── Step 3: 서버 기설치 패키지 제거 ──────────────────────────────────
removed, kept = 0, 0
for whl in glob.glob(f"{PKG_DIR}/*.whl"):
    parts = os.path.basename(whl).split("-")
    if len(parts) >= 2:
        name = parts[0].lower().replace("-", "_")
        ver  = parts[1]
        if server_pkgs.get(name) == ver:
            os.remove(whl)
            print(f"  SKIP (서버 동일버전): {os.path.basename(whl)}")
            removed += 1
            continue
    kept += 1
print(f"[+] 필터 완료 — 제거: {removed}개 / 유지: {kept}개")

# ── 다운로드된 패키지 버전 목록 출력 ─────────────────────────────────
print("\n[+] 포함 패키지 목록:")
for whl in sorted(glob.glob(f"{PKG_DIR}/*.whl")):
    parts = os.path.basename(whl).split("-")
    if len(parts) >= 2:
        print(f"  {parts[0]}-{parts[1]}")

# ── Step 4: Ollama 바이너리 (tar.zst → tar.gz 재압축) ────────────────
print("\n[*] Ollama 바이너리 다운로드 중...")
zst_path = f"{PKG_DIR}/ollama-linux-amd64.tar.zst"
gz_path  = f"{PKG_DIR}/ollama-linux-amd64.tar.gz"

os.system("apt-get install -y zstd > /dev/null 2>&1")
os.system(
    f"wget -q --show-progress "
    f"https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64.tar.zst "
    f"-O {zst_path}"
)

# tar.zst 압축 해제 후 tar.gz 재압축
extract_dir = "/tmp/ollama_extract"
os.system(f"rm -rf {extract_dir} && mkdir -p {extract_dir}")
ret = os.system(f"tar -I zstd -xf {zst_path} -C {extract_dir}")
if ret != 0:
    print("[!] Ollama 압축 해제 실패")
else:
    os.system(f"tar -czf {gz_path} -C {extract_dir} .")
    os.remove(zst_path)

    # 버전 확인 (tar 내부 구조에 무관하게 바이너리 탐색)
    import subprocess
    find = subprocess.run(["find", extract_dir, "-name", "ollama", "-type", "f"],
                          capture_output=True, text=True)
    ollama_bin = find.stdout.strip().split("\n")[0] if find.stdout.strip() else None
    if ollama_bin:
        os.system(f"chmod +x {ollama_bin}")
        ver = subprocess.run([ollama_bin, "--version"], capture_output=True, text=True)
        print(f"[+] Ollama 버전: {ver.stdout.strip() or ver.stderr.strip()}")
    else:
        print("[!] ollama 바이너리를 찾을 수 없음 — 추출 경로 확인:")
        os.system(f"find {extract_dir} -type f | head -20")
    print(f"[+] Ollama tar.gz 재압축 완료: {gz_path}")

# ── Step 5: install.sh 생성 ───────────────────────────────────────────
with open("/content/install.sh", "w", newline="\n") as f:
    f.write(INSTALL_SH)
print("[+] install.sh 생성 완료")

# ── Step 6 & 7: 독립 유효한 tar.gz로 분할 다운로드 ──────────────────
# split 방식(스트림 절단) 대신 각 파트를 독립 tar.gz로 생성 → 보안 장비 통과
all_pkg_files = sorted(glob.glob(f"{PKG_DIR}/*"))
file_sizes    = {f: os.path.getsize(f) for f in all_pkg_files}
total_pkg_size = sum(file_sizes.values())
print(f"\n[+] 전체 패키지 크기: {total_pkg_size / 1024**2:.1f} MB")

# 파일을 1.9GB 이하 청크로 묶기
chunks: list[list[str]] = []
cur_chunk: list[str]   = []
cur_size               = 0
for fp in all_pkg_files:
    fsz = file_sizes[fp]
    if cur_size + fsz > MAX_BYTES and cur_chunk:
        chunks.append(cur_chunk)
        cur_chunk, cur_size = [fp], fsz
    else:
        cur_chunk.append(fp)
        cur_size += fsz
if cur_chunk:
    chunks.append(cur_chunk)

bundle_paths: list[str] = []
for i, chunk in enumerate(chunks):
    part_path  = f"/content/ai_bundle_part{i+1:02d}.tar.gz"
    rel_files  = [os.path.relpath(f, "/content") for f in chunk]
    if i == 0:                        # install.sh는 첫 번째 파트에만 포함
        rel_files = ["install.sh"] + rel_files
    files_str  = " ".join(f'"{f}"' for f in rel_files)
    os.system(f"cd /content && tar -czf {part_path} {files_str}")
    psz = os.path.getsize(part_path)
    print(f"[+] {os.path.basename(part_path)}: {psz / 1024**2:.1f} MB  ({len(chunk)}개 파일)")
    bundle_paths.append(part_path)

print(f"\n[+] 총 {len(bundle_paths)}개 번들 생성 완료")
print("    ── 폐쇄망 설치 순서 ──")
print("    mkdir ai-bundle && cd ai-bundle")
for bp in bundle_paths:
    print(f"    tar -xzf {os.path.basename(bp)}")
print("    chmod +x install.sh && ./install.sh")

for bp in bundle_paths:
    print(f"\n[*] 다운로드: {os.path.basename(bp)}")
    files.download(bp)
