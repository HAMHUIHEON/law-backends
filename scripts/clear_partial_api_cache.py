"""
issue_logic.json 없는(미완료) api_ 케이스의 중간 캐시 파일 삭제.
raw.json / paragraphs.json은 유지 (재사용 가능).
삭제 대상: structure_raw.json 이후 단계들.
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent
CACHE = ROOT / "cache"

STAGE_FILES = [
    "structure_raw.json",
    "structure_type2.json",
    "case_sentences.json",
    "sentence_role.json",
    "bravo_nodes.json",
    "bravo_blocks.json",
    "narrative.json",
    "keyword_map.json",
    "keyword_signature.json",
    "keyword_cluster.json",
    "issue_frame.json",
    "issue_logic.json",
    "issue_logic_citations.json",
    "issue_logic_with_citations.json",
    "statutes.json",
    "metadata.json",
    "final.json",
]

cleared = 0
for case_dir in sorted(CACHE.glob("api_*")):
    if (case_dir / "issue_logic.json").exists():
        continue  # 완료된 케이스는 건드리지 않음
    removed_any = False
    for fname in STAGE_FILES:
        f = case_dir / fname
        if f.exists():
            f.unlink()
            removed_any = True
    if removed_any:
        cleared += 1
        print(f"  정리: {case_dir.name}")

print(f"\n총 {cleared}개 케이스 중간 캐시 정리 완료")
