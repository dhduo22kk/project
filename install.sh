#!/bin/bash
set -e
BUNDLE="$(cd "$(dirname "$0")" && pwd)"

echo "[*] Installing Python packages..."
pip3 install --no-index --find-links="$BUNDLE/packages" \
    faster-whisper ctranslate2 \
    langchain-core langchain langchain-ollama langchain-chroma \
    langgraph langgraph-checkpoint-sqlite ollama \
    chromadb duckdb \
    pymupdf4llm mammoth python-pptx python-docx \
    gradio openpyxl

echo "[*] Installing Ollama..."
sudo tar -xzf "$BUNDLE/packages/ollama-linux-amd64.tar.gz" -C /usr/local/
sudo chmod +x /usr/local/bin/ollama
echo "[+] Ollama 버전: $(/usr/local/bin/ollama --version 2>/dev/null || echo '확인 불가')"

echo "[*] nomic-embed-text Ollama 모델 등록..."
EMBED_GGUF=$(find "$BUNDLE/packages" -name "nomic-embed-text*.gguf" | head -1)
if [ -z "$EMBED_GGUF" ]; then
    echo "[!] nomic-embed-text GGUF 파일을 찾을 수 없음"
else
    echo "FROM $EMBED_GGUF" > /tmp/nomic_Modelfile
    ollama create nomic-embed-text -f /tmp/nomic_Modelfile
    echo "[+] nomic-embed-text 등록 완료"
fi

echo "[+] Done!"
echo "    다음 단계:"
echo "    1) ollama serve &"
echo "    2) ollama create mymodel -f /path/to/Modelfile  # Qwen3.6 모델 등록"
echo "    3) whisper 모델 경로: /opt/models/faster-whisper-large-v3"
