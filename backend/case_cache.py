# case_cache.py
# 판례 분석 결과를 SQLite에 저장/조회하는 캐시 레이어
# case_id를 key로, pipeline 전체 결과를 JSON으로 저장

import sqlite3
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

DB_PATH = Path(__file__).parent / "lapis_cache.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """DB 초기화 — 앱 시작 시 한 번만 호출"""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS case_analysis (
                case_id     TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        conn.commit()


def save_analysis(case_id: str, result: dict) -> None:
    """pipeline 결과를 저장. 이미 있으면 덮어쓴다."""
    now = datetime.utcnow().isoformat()
    data = json.dumps(result, ensure_ascii=False)
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO case_analysis (case_id, result_json, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(case_id) DO UPDATE SET
                result_json = excluded.result_json,
                updated_at  = excluded.updated_at
        """, (case_id, data, now, now))
        conn.commit()


def load_analysis(case_id: str) -> Optional[dict]:
    """캐시에서 결과 조회. 없으면 None."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT result_json FROM case_analysis WHERE case_id = ?",
            (case_id,)
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["result_json"])


def list_cases() -> list[dict]:
    """캐시에 있는 모든 판례 목록 반환"""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT case_id, created_at, updated_at FROM case_analysis ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_analysis(case_id: str) -> bool:
    """캐시에서 특정 판례 삭제. 삭제됐으면 True."""
    with _get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM case_analysis WHERE case_id = ?", (case_id,)
        )
        conn.commit()
    return cur.rowcount > 0


# 모듈 로드 시 자동 초기화
init_db()
