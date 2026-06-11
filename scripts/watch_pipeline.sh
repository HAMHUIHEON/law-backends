#!/bin/bash
# watch_pipeline.sh — 파이프라인 감시 + API 한도 도달 시 자동 벡터 DB 빌드

PIPELINE_LOG="C:/Users/LG/Documents/langchain-kr/29_FINAL/pipeline.log"
MONITOR_LOG="C:/Users/LG/Documents/langchain-kr/29_FINAL/monitor.log"
PYTHON="C:/Users/LG/AppData/Local/pypoetry/Cache/virtualenvs/langchain-kr-0bF25OO7-py3.11/Scripts/python.exe"
VECTOR_SCRIPT="C:/Users/LG/Documents/langchain-kr/29_FINAL/scripts/build_court_vector_db.py"
ROOT="C:/Users/LG/Documents/langchain-kr/29_FINAL"
PIPELINE_PID=5644

api_error_seen=0

trigger_vector_build() {
    echo "[WATCH] API 한도 도달 감지 — 파이프라인 중단 후 벡터 DB 빌드 시작"
    kill $PIPELINE_PID 2>/dev/null
    sleep 3
    echo "[WATCH] build_court_vector_db.py --refresh-api 실행 중..."
    cd "$ROOT"
    "$PYTHON" "$VECTOR_SCRIPT" --refresh-api
    local rc=$?
    if [ $rc -eq 0 ]; then
        echo "[WATCH] ✅ 벡터 DB 빌드 완료"
    else
        echo "[WATCH] ❌ 벡터 DB 빌드 실패 (exit=$rc)"
    fi
    exit 0
}

echo "[WATCH] 시작. PID=$PIPELINE_PID 감시 중..."

tail -f "$PIPELINE_LOG" 2>/dev/null | while IFS= read -r line; do
    # 진행 완료 라인
    if echo "$line" | grep -qE "\[완료\]"; then
        echo "$line"
    fi

    # API 한도 / rate limit 에러
    if echo "$line" | grep -qiE "RateLimitError|insufficient_quota|quota.*exceeded|rate.limit|429|billing|credit"; then
        echo "[WATCH] ⚠️  API 한도 감지: $line"
        api_error_seen=1
        trigger_vector_build
    fi

    # 파이프라인 정상 완료
    if echo "$line" | grep -qE "완료 — 성공"; then
        echo "[WATCH] ✅ 파이프라인 정상 완료: $line"
        exit 0
    fi

    # 오류 라인 보고
    if echo "$line" | grep -qE "^\s+\[오류\]"; then
        echo "$line"
    fi
done &

# monitor.log도 병행 감시
tail -f "$MONITOR_LOG" 2>/dev/null | while IFS= read -r line; do
    if echo "$line" | grep -qE "완료|재빌드|✅|❌|696"; then
        echo "[MON] $line"
    fi
done
