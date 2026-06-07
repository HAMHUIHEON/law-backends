import os
from dotenv import load_dotenv
load_dotenv('../.env')

from db.graph_search import LegalGraphSearch

searcher = LegalGraphSearch()

print("=" * 60)
print("[1] 유사 쟁점 검색")
print("=" * 60)
results = searcher.search_similar_issues(
    "특수관계자 간 자산 저가양도가 부당행위계산 부인 대상인지",
    top_k=5
)
for r in results:
    print(f"  {r['case_number']}  유사도={r['similarity']}  {r['issue'][:60]}")

print()
print("=" * 60)
print("[2] 법령 기반 판례 탐색 - 법인세법")
print("=" * 60)
cases = searcher.get_statute_cases("법인세법")
for c in cases[:5]:
    print(f"  {c['judgment_date']}  {c['case_number']}  {c['issue'][:40]}")

print()
print("=" * 60)
print("[3] 승소 패턴 분석")
print("=" * 60)
pattern = searcher.analyze_winning_patterns(
    "해외 특수관계자 이전가격 정상가격 산출",
    top_k=10
)
print(f"  유사 쟁점 {len(pattern['similar_issues'])}건 검색됨")
print("  가장 많이 인용된 법령:")
for s in pattern["statutes_cited"]:
    print(f"    {s['statute']} - {s['freq']}회")

searcher.close()
print("\n[완료]")
