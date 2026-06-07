"""법령 버전 조회 단건 테스트"""
import os, sys, json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

from utils.statute_version import lookup_itcl_version, lookup_general_law_version

# 테스트 1: ITCL 법률 제15221호 이전 버전 (Neo4j에 없는 2017년 버전)
print("=== TEST 1: 구 국제조세조정법 제5조 (법률 제15221호로 개정되기 전) ===")
r1 = lookup_itcl_version("15221", "법률")
print(json.dumps(r1, ensure_ascii=False, indent=2) if r1 else "None")

print()

# 테스트 2: Neo4j에 있는 버전 (2021년 이후)
print("=== TEST 2: Neo4j 보유 버전 확인 (법률 제17651호) ===")
r2 = lookup_itcl_version("17651", "법률")
print(json.dumps(r2, ensure_ascii=False, indent=2) if r2 else "None - not in DB")

print()

# 테스트 3: Claude 지식으로 구 법인세법 제41조 조회
print("=== TEST 3: 구 법인세법 제41조 제1항 제3호 (법률 제16008호로 개정되기 전) ===")
r3 = lookup_general_law_version(
    title="구 법인세법 제41조 제1항 제3호",
    promulgation_no="16008",
    promulgation_type="법률",
    effective_before="2018-12-24",
    article_ref="법인세법 제41조 제1항 제3호",
)
print(json.dumps(r3, ensure_ascii=False, indent=2))
