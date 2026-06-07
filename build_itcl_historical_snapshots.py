"""
ITCL 역사적 IntegratedSnapshot 빌더 (경량 버전)

law/itcl/{law,decree,rule}/ 폴더의 모든 버전 파일을 읽어
각 변경 시점마다 유효한 (law, decree, rule) 조합을 계산하고,
Neo4j에 IntegratedSnapshot 노드(set_key + valid_from + valid_to)만 삽입합니다.

LLM 파이프라인 없이 순수 메타데이터만 삽입 → citation version lookup이 목적.

실행:
    python build_itcl_historical_snapshots.py
    python build_itcl_historical_snapshots.py --dry-run   # Neo4j 쓰기 없이 목록만 출력
"""

import argparse
import json
import os
import sys
from pathlib import Path

import dotenv
dotenv.load_dotenv()

ROOT = Path(__file__).parent
ITCL_DIR = ROOT / "law" / "itcl"


# ─────────────────────────────────────────────────────────
# 1. 파일 읽기
# ─────────────────────────────────────────────────────────

def read_version_files(subfolder: str) -> list[dict]:
    """law/itcl/{subfolder}/ 에서 (date, no) 추출, 날짜순 정렬"""
    d = ITCL_DIR / subfolder
    if not d.exists():
        print(f"[WARN] 폴더 없음: {d}")
        return []

    result = []
    for f in sorted(d.glob("*.json")):
        raw = json.loads(f.read_text(encoding="utf-8"))
        first_key = next(iter(raw))
        info = raw[first_key].get("기본정보", {})
        pdate = info.get("공포일자", "").strip()
        pno   = info.get("공포번호", "").strip()
        if pdate and pno:
            result.append({
                "date": pdate,   # "20171219"
                "no":   pno,     # "15221" or "00613"
                "scope": subfolder.upper(),  # "LAW" / "DECREE" / "RULE"
                "file":  str(f),
            })
        else:
            print(f"  [SKIP] 기본정보 없음: {f.name}")

    result.sort(key=lambda x: x["date"])
    return result


# ─────────────────────────────────────────────────────────
# 2. 변경 시점 조합 계산
# ─────────────────────────────────────────────────────────

def _current_at(items: list[dict], date: str) -> dict | None:
    """date 이하인 가장 최신 item 반환"""
    valid = [x for x in items if x["date"] <= date]
    return valid[-1] if valid else None


def build_historical_snapshots(laws, decrees, rules) -> list[dict]:
    """
    모든 변경 날짜(법/령/규칙 공포일 합집합)에서
    당시 유효한 (law, decree, rule) 조합을 계산해 스냅샷 목록 반환.

    - rule이 없는 시기(rule 첫 공포일 이전)는 제외
    - 동일 조합이 반복되면 하나의 스냅샷으로 합침
    """
    if not rules:
        print("[ERROR] rule 파일이 없습니다.")
        return []

    first_rule_date = rules[0]["date"]

    # 모든 변경 날짜 수집
    all_dates = sorted(set(
        [x["date"] for x in laws] +
        [x["date"] for x in decrees] +
        [x["date"] for x in rules]
    ))

    seen: set[str] = set()
    snapshots: list[dict] = []

    for date in all_dates:
        if date < first_rule_date:
            continue  # rule 없는 시기 스킵

        law    = _current_at(laws,    date)
        decree = _current_at(decrees, date)
        rule   = _current_at(rules,   date)

        if not (law and decree and rule):
            continue

        set_key = (
            f"LAW_{law['date']}_{law['no']}"
            f"__DECREE_{decree['date']}_{decree['no']}"
            f"__RULE_{rule['date']}_{rule['no']}"
        )

        if set_key not in seen:
            seen.add(set_key)
            snapshots.append({
                "set_key":      set_key,
                "valid_from":   date,         # 이 조합이 처음 유효해진 날
                "law_no":       law["no"],
                "decree_no":    decree["no"],
                "rule_no":      rule["no"],
                "law_date":     law["date"],
                "decree_date":  decree["date"],
                "rule_date":    rule["date"],
            })

    # valid_to 계산
    for i, snap in enumerate(snapshots):
        snap["valid_to"] = snapshots[i + 1]["valid_from"] if i + 1 < len(snapshots) else None

    return snapshots


# ─────────────────────────────────────────────────────────
# 3. Neo4j 삽입
# ─────────────────────────────────────────────────────────

def ingest_snapshots(snapshots: list[dict], driver) -> tuple[int, int]:
    """
    IntegratedSnapshot 노드를 MERGE 로 삽입.
    기존 노드(이미 Neo4j에 있는 것)는 valid_from/valid_to를 덮어쓰지 않음.
    신규 노드에만 ON CREATE SET 적용.
    """
    created = 0
    skipped = 0

    with driver.session() as session:
        for snap in snapshots:
            result = session.run(
                """
                MERGE (s:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
                ON CREATE SET
                    s.valid_from      = $valid_from,
                    s.valid_to        = $valid_to,
                    s.promulgated_at  = $law_date,
                    s.effective_at    = $law_date,
                    s.law_version_key = $law_vkey,
                    s.decree_version_key = $decree_vkey,
                    s.rule_version_key   = $rule_vkey,
                    s.source = "historical_builder"
                RETURN (count(s) > 0) AS merged
                """,
                set_key     = snap["set_key"],
                valid_from  = snap["valid_from"],
                valid_to    = snap["valid_to"],
                law_date    = snap["law_date"],
                law_vkey    = f"{snap['law_date']}_{snap['law_no']}",
                decree_vkey = f"{snap['decree_date']}_{snap['decree_no']}",
                rule_vkey   = f"{snap['rule_date']}_{snap['rule_no']}",
            )
            # MERGE는 항상 노드를 반환하므로 created/skipped 구분은 별도 체크
            skipped_flag = session.run(
                """
                MATCH (s:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
                WHERE s.source IS NOT NULL AND s.source = "historical_builder"
                RETURN count(s) AS cnt
                """,
                set_key=snap["set_key"],
            ).single()["cnt"]

            if skipped_flag:
                created += 1
            else:
                skipped += 1

    return created, skipped


def ingest_snapshots_simple(snapshots: list[dict], driver) -> tuple[int, int]:
    """
    간단 버전: ON CREATE SET으로 기존 노드 보호 + 신규 생성 카운트.
    (위 함수는 2-query 방식이라 느릴 수 있어 단순화)
    """
    created = 0
    existing = 0

    with driver.session() as session:
        # 기존 set_key 목록 가져오기
        existing_keys = {
            r["sk"]
            for r in session.run(
                "MATCH (s:IntegratedSnapshot {scope:'INTEGRATED'}) RETURN s.set_key AS sk"
            )
        }

    with driver.session() as session:
        for snap in snapshots:
            if snap["set_key"] in existing_keys:
                existing += 1
                continue

            session.run(
                """
                MERGE (s:IntegratedSnapshot {scope:"INTEGRATED", set_key:$set_key})
                ON CREATE SET
                    s.valid_from         = $valid_from,
                    s.valid_to           = $valid_to,
                    s.promulgated_at     = $law_date,
                    s.effective_at       = $law_date,
                    s.law_version_key    = $law_vkey,
                    s.decree_version_key = $decree_vkey,
                    s.rule_version_key   = $rule_vkey,
                    s.source             = "historical_builder"
                """,
                set_key     = snap["set_key"],
                valid_from  = snap["valid_from"],
                valid_to    = snap["valid_to"],
                law_date    = snap["law_date"],
                law_vkey    = f"{snap['law_date']}_{snap['law_no']}",
                decree_vkey = f"{snap['decree_date']}_{snap['decree_no']}",
                rule_vkey   = f"{snap['rule_date']}_{snap['rule_no']}",
            )
            created += 1

    return created, existing


# ─────────────────────────────────────────────────────────
# 4. 메인
# ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Neo4j에 쓰지 않고 생성될 스냅샷 목록만 출력")
    args = parser.parse_args()

    print("=== ITCL 역사적 스냅샷 빌더 ===\n")

    # 파일 읽기
    laws    = read_version_files("law")
    decrees = read_version_files("decree")
    rules   = read_version_files("rule")

    print(f"law 버전: {len(laws)}개  ({laws[0]['date']} ~ {laws[-1]['date']})")
    print(f"decree 버전: {len(decrees)}개  ({decrees[0]['date']} ~ {decrees[-1]['date']})")
    print(f"rule 버전: {len(rules)}개  ({rules[0]['date']} ~ {rules[-1]['date']})")
    print()

    # 조합 계산
    snapshots = build_historical_snapshots(laws, decrees, rules)
    print(f"계산된 스냅샷 조합: {len(snapshots)}개\n")

    for snap in snapshots:
        flag = "  "
        # 중요: 2022구합7106 참조 공포번호 표시
        if any(no in snap["set_key"] for no in ["15221", "27837", "29525"]):
            flag = "* "  # 테스트 케이스 관련
        print(
            f"{flag}[{snap['valid_from']} ~ {snap['valid_to'] or '현재'}] "
            f"{snap['set_key']}"
        )

    print()

    if args.dry_run:
        print("[DRY-RUN] Neo4j 삽입 건너뜀.")
        return

    # Neo4j 삽입
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )

    print("Neo4j에 삽입 중...")
    created, existing = ingest_snapshots_simple(snapshots, driver)
    driver.close()

    print(f"\n완료: 신규 생성 {created}개 / 기존 노드 유지 {existing}개")
    print(f"총 IntegratedSnapshot: {created + existing}개")


if __name__ == "__main__":
    main()
