"""
--all 파이프라인 완료 후 자동 실행 스크립트

순서:
  1. ingest_norm_history --all   : 전 법령 역사 버전 Lite 인제스트 (LLM 없음)
  2. expand_crossrefs --run      : cross-ref 미보유 법령 다운로드 + 인제스트
  3. resolve_crossrefs --run     : 시행일자 기준 Article/Paragraph RESOLVES_TO 연결
  4. verify                      : Neo4j 연결 현황 검증 리포트 출력

실행:
  python -m scripts.run_post_pipeline
"""
import sys, subprocess, time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT   = Path(__file__).parent.parent
PYTHON = sys.executable

STEPS = [
    ("역사 버전 Lite 인제스트",          [PYTHON, "-m", "LAW_7.ingest_norm_history",  "--all"]),
    ("CrossRef 미보유 법령 다운/인제스트", [PYTHON, "-m", "scripts.expand_crossrefs",   "--run"]),
    ("CrossRef RESOLVES_TO 연결",        [PYTHON, "-m", "scripts.resolve_crossrefs",  "--run"]),
]

def run_step(label: str, cmd: list[str]) -> bool:
    print(f"\n{'='*60}")
    print(f"▶ {label}")
    print(f"{'='*60}")
    t0 = time.time()
    result = subprocess.run(cmd, cwd=str(ROOT), env=None)
    elapsed = time.time() - t0
    if result.returncode == 0:
        print(f"✅ {label} 완료 ({elapsed:.0f}s)")
        return True
    else:
        print(f"❌ {label} 실패 (exit={result.returncode}, {elapsed:.0f}s)")
        return False

def verify():
    print(f"\n{'='*60}")
    print("▶ Neo4j 연결 현황 검증")
    print(f"{'='*60}")
    import os, dotenv
    dotenv.load_dotenv()
    import neo4j
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USERNAME", "neo4j"), os.getenv("NEO4J_PASSWORD")),
    )
    with driver.session() as s:
        # 노드 수
        rows = s.run("MATCH (n) RETURN labels(n)[0] AS lbl, count(n) AS cnt ORDER BY cnt DESC")
        print("\n[노드 현황]")
        for r in rows:
            print(f"  {r['lbl']:30s}  {r['cnt']:>7,}")

        # Law 목록
        print("\n[Law 목록]")
        rows = s.run("MATCH (l:Law) RETURN l.scope, l.name, count{(l)-[:HAS_VERSION]->()} AS vers ORDER BY l.scope, l.name")
        for r in rows:
            print(f"  [{r['l.scope']}] {r['l.name']:30s}  {r['vers']}버전")

        # CrossRef 해소율
        rows = s.run("""
            MATCH (lt:LawTarget)
            WITH count(lt) AS total
            MATCH (lt2:LawTarget)-[:RESOLVES_TO]->()
            RETURN total, count(DISTINCT lt2) AS resolved
        """)
        r = list(rows)
        if r:
            total    = r[0]["total"]
            resolved = r[0]["resolved"]
            pct      = resolved / total * 100 if total else 0
            print(f"\n[CrossRef 해소율]")
            print(f"  전체  : {total:,}")
            print(f"  연결됨: {resolved:,}  ({pct:.1f}%)")

        # Paragraph 레벨 연결
        rows = s.run("MATCH ()-[:RESOLVES_TO_PARA]->() RETURN count(*) AS cnt")
        r = list(rows)
        if r:
            print(f"  Paragraph 레벨: {r[0]['cnt']:,}건")

    driver.close()
    print("\n✅ 검증 완료")

if __name__ == "__main__":
    print("🚀 Post-pipeline 자동 처리 시작")
    print(f"   시작 시각: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    for label, cmd in STEPS:
        ok = run_step(label, cmd)
        if not ok:
            print(f"\n⚠️  {label} 에서 오류 발생. 다음 단계로 계속 진행.")

    verify()

    print(f"\n🎉 전체 완료  {time.strftime('%Y-%m-%d %H:%M:%S')}")
