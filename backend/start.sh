#!/bin/bash
# start.sh — Railway cold-start: Chroma Volume 체크 후 uvicorn 시작

set -e

CHROMA_DIR="${CHROMA_DIR:-/app/chroma}"
CHROMA_URL="${CHROMA_DOWNLOAD_URL:-}"

if [ ! -f "$CHROMA_DIR/chroma.sqlite3" ]; then
    echo "[start.sh] Chroma 데이터 없음"

    if [ -z "$CHROMA_URL" ]; then
        echo "[start.sh] 경고: CHROMA_DOWNLOAD_URL 없음. Chroma 없이 시작."
    else
        mkdir -p "$CHROMA_DIR"
        echo "[start.sh] 다운로드: $CHROMA_URL"
        curl -L --retry 3 --retry-delay 5 -o /tmp/chroma_data.zip "$CHROMA_URL"
        echo "[start.sh] 압축 해제 중..."
        python3 -c "
import zipfile
with zipfile.ZipFile('/tmp/chroma_data.zip') as zf:
    for member in zf.infolist():
        member.filename = member.filename.replace('\\\\', '/')
        zf.extract(member, '$CHROMA_DIR')
print('압축 해제 완료')
"
        rm /tmp/chroma_data.zip
        echo "[start.sh] Chroma 준비 완료"
    fi
else
    echo "[start.sh] Chroma 데이터 존재 — 다운로드 생략"
fi

echo "[start.sh] uvicorn 시작"
exec python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
