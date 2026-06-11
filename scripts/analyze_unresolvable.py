"""UNRESOLVABLE LawTarget 법령명별 집계 — 다운로드 우선순위 파악."""
import sys, os, re
sys.stdout.reconfigure(encoding='utf-8')
import dotenv; dotenv.load_dotenv()
from neo4j import GraphDatabase
from collections import Counter

URI = os.getenv('NEO4J_URI')
AUTH = (os.getenv('NEO4J_USERNAME', 'neo4j'), os.getenv('NEO4J_PASSWORD'))
d = GraphDatabase.driver(URI, auth=AUTH)

with d.session() as s:
    rows = s.run("""
        MATCH (lt:LawTarget)
        WHERE lt.resolved_version_key = 'UNRESOLVABLE'
        RETURN lt.name AS target, lt.unresolvable_reason AS reason
    """).data()

# 법령명 추출 패턴
LAW_RE = re.compile(
    r'[「『]?([가-힣\s]+(?:법|령|규칙|조례)(?:\s*시행령|\s*시행규칙)?)[」』]?'
)

reason_counts = Counter(r['reason'] for r in rows)
print(f"UNRESOLVABLE 전체: {len(rows)}건\n")
print("=== 미해소 사유 ===")
for reason, cnt in reason_counts.most_common():
    print(f"  {reason or 'None':25s}: {cnt:5d}건")

# 외부참조 미해소 대상 법령 집계
print("\n=== 외부 법령 미해소 (not_found) — 다운로드 우선순위 ===")
not_found = [r for r in rows if r['reason'] == 'not_found']
law_counter = Counter()
for r in not_found:
    target = r['target']
    m = LAW_RE.search(target)
    if m:
        law_name = m.group(1).strip()
        law_counter[law_name] += 1

for law, cnt in law_counter.most_common(30):
    print(f"  {law:40s}: {cnt:4d}건")

d.close()
