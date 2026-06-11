"""
IntegratedSnapshot 노드의 valid_from / valid_to 수정

DRF 원본 파일에서 시행일(effective_at)을 읽어 3-way overlap 계산 후 Neo4j 업데이트.
cypher.py의 11개 known 값과 교차 검증 후 진행.
"""
import os, json, sys
from pathlib import Path
from itertools import product as cart_product
from dataclasses import dataclass
from typing import Optional

import dotenv
dotenv.load_dotenv()

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from neo4j import GraphDatabase

# ──────────────────────────────────────────────────────────────
# 1. DRF 파일에서 버전 메타 읽기
# ──────────────────────────────────────────────────────────────

@dataclass
class VerMeta:
    promulgated_at: str   # 공포일자 YYYYMMDD
    promulgation_no: str  # 공포번호 (문자열 그대로, 예 "00840")
    effective_at: str     # 시행일자 YYYYMMDD

def read_drfs(subdir: str) -> list[VerMeta]:
    metas = []
    for fpath in (ROOT / "law/itcl" / subdir).glob("*.json"):
        with open(fpath, encoding="utf-8") as f:
            d = json.load(f)
        base = d["법령"]["기본정보"]
        metas.append(VerMeta(
            promulgated_at=str(base["공포일자"]),
            promulgation_no=str(base["공포번호"]),
            effective_at=str(base.get("시행일자") or base["공포일자"]),
        ))
    return sorted(metas, key=lambda m: m.effective_at)

laws   = read_drfs("law")
decrees = read_drfs("decree")
rules  = read_drfs("rule")

# ──────────────────────────────────────────────────────────────
# 2. valid_from/valid_to 계산 (build_version_windows 로직)
# ──────────────────────────────────────────────────────────────

@dataclass
class VerWindow(VerMeta):
    valid_from: str
    valid_to: Optional[str]

def build_windows(metas: list[VerMeta]) -> list[VerWindow]:
    metas = sorted(metas, key=lambda m: m.effective_at)
    seen_effective = {}  # effective_at → latest promulgation
    # 같은 effective_at가 있으면 공포번호가 큰 것이 최신
    for m in metas:
        existing = seen_effective.get(m.effective_at)
        if existing is None or m.promulgation_no > existing.promulgation_no:
            seen_effective[m.effective_at] = m
    unique = sorted(seen_effective.values(), key=lambda m: m.effective_at)

    windows = []
    for i, v in enumerate(unique):
        valid_to = unique[i + 1].effective_at if i + 1 < len(unique) else None
        windows.append(VerWindow(
            promulgated_at=v.promulgated_at,
            promulgation_no=v.promulgation_no,
            effective_at=v.effective_at,
            valid_from=v.effective_at,
            valid_to=valid_to,
        ))
    return windows

def overlap(a_from, a_to, b_from, b_to):
    start = max(a_from, b_from)
    end = min(a_to or "99991231", b_to or "99991231")
    if start < end:
        return start, None if end == "99991231" else end
    return None, None

law_wins   = build_windows(laws)
decree_wins = build_windows(decrees)
rule_wins  = build_windows(rules)

print(f"LAW 버전 {len(law_wins)}개 / DECREE {len(decree_wins)}개 / RULE {len(rule_wins)}개")

# ──────────────────────────────────────────────────────────────
# 3. 3-way overlap → Neo4j set_key 매핑 구성
# ──────────────────────────────────────────────────────────────

def neo4j_set_key(l: VerWindow, d: VerWindow, r: VerWindow) -> str:
    return (f"LAW_{l.promulgated_at}_{l.promulgation_no}__"
            f"DECREE_{d.promulgated_at}_{d.promulgation_no}__"
            f"RULE_{r.promulgated_at}_{r.promulgation_no}")

computed: dict[str, tuple[str, Optional[str]]] = {}

for l, d, r in cart_product(law_wins, decree_wins, rule_wins):
    s1, e1 = overlap(l.valid_from, l.valid_to, d.valid_from, d.valid_to)
    if not s1:
        continue
    s2, e2 = overlap(s1, e1, r.valid_from, r.valid_to)
    if not s2:
        continue
    sk = neo4j_set_key(l, d, r)
    computed[sk] = (s2, e2)

print(f"계산된 유효 3-way 조합: {len(computed)}개\n")

# ──────────────────────────────────────────────────────────────
# 4. cypher.py known 값과 교차 검증
# ──────────────────────────────────────────────────────────────

KNOWN = {
    "LAW_20201222_17651__DECREE_20210217_31448__RULE_20210316_00840": ("20210316", "20211230"),
    "LAW_20201222_17651__DECREE_20211228_32274__RULE_20210316_00840": ("20211230", "20220101"),
    "LAW_20211221_18588__DECREE_20211228_32274__RULE_20210316_00840": ("20220101", "20220215"),
    "LAW_20211221_18588__DECREE_20220215_32423__RULE_20210316_00840": ("20220215", "20220318"),
    "LAW_20211221_18588__DECREE_20220215_32423__RULE_20220318_00901": ("20220318", "20221227"),
    "LAW_20211221_18588__DECREE_20221227_33140__RULE_20220318_00901": ("20221227", "20230101"),
    "LAW_20221231_19191__DECREE_20221227_33140__RULE_20220318_00901": ("20230101", "20230228"),
    "LAW_20221231_19191__DECREE_20230228_33272__RULE_20220318_00901": ("20230228", "20230320"),
    "LAW_20221231_19191__DECREE_20230228_33272__RULE_20230320_00983": ("20230320", "20240101"),
    "LAW_20231231_19928__DECREE_20231229_34064__RULE_20230320_00983": ("20240101", "20240229"),
    "LAW_20231231_19928__DECREE_20240229_34264__RULE_20230320_00983": ("20240229", "20240322"),
}

print("=== cypher.py known 값 교차 검증 ===")
all_ok = True
for sk, (exp_from, exp_to) in KNOWN.items():
    got = computed.get(sk)
    if got is None:
        print(f"  ❌ MISSING  {sk}")
        all_ok = False
    elif got != (exp_from, exp_to):
        print(f"  ❌ MISMATCH {sk}")
        print(f"     expected: {exp_from} → {exp_to}")
        print(f"     computed: {got[0]} → {got[1]}")
        all_ok = False
    else:
        print(f"  ✅ {sk[-60:]}: {exp_from} → {exp_to}")

if not all_ok:
    print("\n⚠️  검증 실패 — Neo4j 업데이트 중단.")
    sys.exit(1)

print("\n✅ 모든 known 값 검증 통과\n")

# ──────────────────────────────────────────────────────────────
# 5. Neo4j의 현재 IntegratedSnapshot 목록 조회
# ──────────────────────────────────────────────────────────────

driver = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
)

print("=== Neo4j IntegratedSnapshot 현재 상태 ===")
with driver.session() as s:
    rows = s.run(
        "MATCH (n:IntegratedSnapshot) RETURN n.set_key AS sk, n.valid_from AS vf, n.valid_to AS vt"
    ).data()

neo4j_keys = {r["sk"] for r in rows}
print(f"Neo4j에 있는 set_key: {len(neo4j_keys)}개\n")

# ──────────────────────────────────────────────────────────────
# 6. 업데이트할 목록 확인
# ──────────────────────────────────────────────────────────────

updates = []
missing_from_computed = []

for sk in sorted(neo4j_keys):
    if sk not in computed:
        missing_from_computed.append(sk)
    else:
        vf, vt = computed[sk]
        updates.append({"sk": sk, "vf": vf, "vt": vt})

if missing_from_computed:
    print("⚠️  계산에서 누락된 set_key (Neo4j에 있지만 3-way 계산 결과에 없음):")
    for sk in missing_from_computed:
        print(f"  {sk}")
    print()

print(f"업데이트할 노드: {len(updates)}개\n")
for u in updates:
    print(f"  {u['sk'][-70:]}: {u['vf']} → {u['vt']}")

# ──────────────────────────────────────────────────────────────
# 7. Neo4j 업데이트
# ──────────────────────────────────────────────────────────────

print("\n=== Neo4j valid_from / valid_to 업데이트 시작 ===")
ok = 0
with driver.session() as s:
    for u in updates:
        result = s.run(
            """
            MATCH (n:IntegratedSnapshot {set_key: $sk})
            SET n.valid_from = $vf, n.valid_to = $vt
            RETURN count(n) AS updated
            """,
            sk=u["sk"], vf=u["vf"], vt=u["vt"]
        )
        cnt = result.single()["updated"]
        if cnt > 0:
            print(f"  ✅ {u['sk'][-65:]}: {u['vf']} → {u['vt']}")
            ok += 1
        else:
            print(f"  ⚠️  매칭 없음: {u['sk']}")

driver.close()
print(f"\n완료: {ok}/{len(updates)}개 업데이트됨")
