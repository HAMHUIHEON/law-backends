"""
세법 역사적 버전 다운로더 + Neo4j LawVersion 노드 빌더

대상 법령:
  - 국세기본법
  - 국세징수법
  - 법인세법
  - 소득세법
  - 부가가치세법
  - 조세범처벌법
  - 조세범처벌절차법

실행:
  python build_law_history_db.py --download       # API에서 다운로드만
  python build_law_history_db.py --ingest         # Neo4j 삽입만
  python build_law_history_db.py --all            # 다운로드 + 삽입
  python build_law_history_db.py --all --law 국세기본법  # 특정 법령만
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import dotenv
dotenv.load_dotenv()

import requests
import urllib3
urllib3.disable_warnings()

OC = "seungmi0723"
BASE_URL = "http://www.law.go.kr/DRF"
ROOT = Path(__file__).parent.parent
LAW_DIR = ROOT / "law"

LAWS = [
    {"name": "국세기본법",      "slug": "gukse_basic"},
    {"name": "국세징수법",      "slug": "gukse_collection"},
    {"name": "법인세법",        "slug": "corporate_tax"},
    {"name": "소득세법",        "slug": "income_tax"},
    {"name": "부가가치세법",    "slug": "vat"},
    {"name": "조세범처벌법",    "slug": "tax_crime"},
    {"name": "조세범처벌절차법", "slug": "tax_crime_proc"},
]

session = requests.Session()
session.verify = False
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


# ─────────────────────────────────────────────────────────
# 1. MST 목록 수집 (lsHistory HTML 파싱)
# ─────────────────────────────────────────────────────────

def fetch_mst_list(law_name: str) -> list[str]:
    """lsHistory HTML에서 해당 법령의 MST 목록 추출"""
    msts = []
    page = 1
    while True:
        params = {
            "OC": OC,
            "target": "lsHistory",
            "type": "HTML",
            "query": law_name,
            "display": 100,
            "page": page,
        }
        try:
            resp = session.get(f"{BASE_URL}/lawSearch.do", params=params,
                               headers=HEADERS, timeout=15)
            html = resp.text
        except Exception as e:
            print(f"  [ERR] lsHistory 요청 실패: {e}")
            break

        # MST+법령명 추출
        rows = re.findall(r'MST=(\d+)[^"]*"[^>]*>([^<]+)</a>', html)
        if not rows:
            break

        page_msts = [mst for mst, name in rows if law_name in name.strip()]
        if not page_msts:
            break

        msts.extend(page_msts)
        print(f"    page {page}: {len(page_msts)}개 MST ({len(msts)}개 누적)")

        if len(page_msts) < 100:
            break
        page += 1
        time.sleep(0.3)

    return msts


# ─────────────────────────────────────────────────────────
# 2. 개별 버전 다운로드 (lawService JSON)
# ─────────────────────────────────────────────────────────

def fetch_law_version(mst: str, retries: int = 3) -> dict | None:
    """MST 번호로 법령 JSON 다운로드 (재시도 포함)"""
    params = {"OC": OC, "target": "law", "MST": mst, "type": "JSON"}
    for attempt in range(retries):
        try:
            sess = requests.Session()
            sess.verify = False
            resp = sess.get(f"{BASE_URL}/lawService.do", params=params,
                            headers=HEADERS, timeout=20)
            if resp.status_code == 200 and len(resp.text) > 100:
                return resp.json()
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1 + attempt)
            else:
                print(f"    [ERR] MST={mst} 다운로드 실패: {type(e).__name__}")
    return None


def extract_meta(data: dict) -> dict | None:
    """JSON에서 기본정보 추출 (공포일자, 공포번호, 법령명 등)

    API JSON 구조:
      {"법령": {"기본정보": {"법령명_한글": ..., "공포번호": ..., "공포일자": ...}}}
    """
    if not data:
        return None
    first_key = next(iter(data), None)
    if not first_key:
        return None
    root = data[first_key]
    info = root.get("기본정보", {})
    if not info:
        return None

    # 법령명: 한글 우선
    law_name = (
        info.get("법령명_한글")
        or info.get("법령명")
        or first_key
    )
    if isinstance(law_name, str):
        law_name = law_name.strip()

    # 법종구분: dict{"content":"법률"} 또는 문자열
    law_type = info.get("법종구분", "")
    if isinstance(law_type, dict):
        law_type = law_type.get("content", "")
    law_type = str(law_type).strip()

    # MST: 법령키 또는 법령ID
    mst = info.get("법령MST") or info.get("법령키") or info.get("법령ID") or ""
    if isinstance(mst, dict):
        mst = str(mst)

    pno = str(info.get("공포번호", "")).strip()
    pdate = str(info.get("공포일자", "")).strip()
    eff_date = str(info.get("시행일자", "")).strip()

    if not (pdate and pno):
        return None

    return {
        "law_name": law_name,
        "pdate":    pdate,
        "pno":      pno,
        "eff_date": eff_date,
        "law_type": law_type,
        "mst":      str(mst),
    }


# ─────────────────────────────────────────────────────────
# 3. 로컬 저장
# ─────────────────────────────────────────────────────────

def classify_law_name(law_name: str, base_name: str) -> str:
    """법령명 → law/decree/rule 분류"""
    if "시행규칙" in law_name:
        return "rule"
    if "시행령" in law_name:
        return "decree"
    return "law"


def download_law(law_info: dict) -> Path:
    """법령 1개의 모든 역사 버전을 다운로드하여 로컬 저장.

    lsHistory에서 법/령/규칙 MST를 한번에 받아
    법령명 기준으로 law/ decree/ rule/ 서브폴더에 분류 저장.
    """
    name = law_info["name"]
    slug = law_info["slug"]
    out_dir = LAW_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("law", "decree", "rule"):
        (out_dir / sub).mkdir(exist_ok=True)

    # MST 목록 파일 (캐시)
    mst_cache = out_dir / "_mst_list.json"

    print(f"\n[{name}] MST 목록 조회 중...")
    if mst_cache.exists():
        msts = json.loads(mst_cache.read_text(encoding="utf-8"))
        print(f"  캐시에서 {len(msts)}개 MST 로드")
    else:
        msts = fetch_mst_list(name)
        mst_cache.write_text(json.dumps(msts, ensure_ascii=False), encoding="utf-8")
        print(f"  총 {len(msts)}개 MST 발견")

    # 각 버전 다운로드
    downloaded = 0
    skipped = 0
    errors = 0

    for i, mst in enumerate(msts):
        # 이미 어떤 서브폴더에든 있으면 스킵
        existing = list(out_dir.glob(f"*/MST_{mst}.json"))
        if existing:
            skipped += 1
            continue

        print(f"  [{i+1}/{len(msts)}] MST={mst} 다운로드...", end=" ", flush=True)
        data = fetch_law_version(mst)
        if data:
            meta = extract_meta(data)
            if meta:
                sub = classify_law_name(meta["law_name"], name)
                out_file = out_dir / sub / f"MST_{mst}.json"
                out_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                print(f"OK [{sub}] {meta['law_name']} {meta['pdate']} 제{meta['pno']}호")
            else:
                # meta 없으면 law/ 에 저장
                (out_dir / "law" / f"MST_{mst}.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print("OK (meta 없음 → law/)")
            downloaded += 1
        else:
            errors += 1
            print("FAIL")

        time.sleep(0.4)  # API 부하 방지

    print(f"\n  [{name}] 완료: 신규 {downloaded}개 / 스킵 {skipped}개 / 오류 {errors}개")
    return out_dir


# ─────────────────────────────────────────────────────────
# 4. Neo4j 삽입
# ─────────────────────────────────────────────────────────

def load_versions_from_dir(out_dir: Path, subdir: str = "law") -> list[dict]:
    """저장된 JSON 파일에서 버전 메타 목록 반환 (날짜 정렬)

    subdir: "law" | "decree" | "rule"
    """
    target_dir = out_dir / subdir if (out_dir / subdir).exists() else out_dir
    versions = []
    for f in target_dir.glob("MST_*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            meta = extract_meta(data)
            if meta and meta["pdate"] and meta["pno"]:
                meta["file"] = f.name  # 파일명만 (경로 제외)
                meta["subdir"] = subdir
                versions.append(meta)
        except Exception as e:
            print(f"  [SKIP] {f.name}: {e}")

    versions.sort(key=lambda x: x["pdate"])
    return versions


def ingest_law_versions(versions: list[dict], law_name: str, driver) -> tuple[int, int]:
    """LawVersion 노드를 Neo4j에 삽입"""
    created = 0
    existing = 0

    with driver.session() as session:
        existing_keys = {
            r["k"]
            for r in session.run(
                "MATCH (v:LawVersion {law_name:$name}) RETURN v.version_key AS k",
                {"name": law_name},
            )
        }

    with driver.session() as session:
        for v in versions:
            vkey = f"{v['pdate']}_{v['pno']}"
            if vkey in existing_keys:
                existing += 1
                continue

            session.run(
                """
                MERGE (v:LawVersion {law_name:$law_name, version_key:$vkey})
                ON CREATE SET
                    v.promulgation_date = $pdate,
                    v.promulgation_no   = $pno,
                    v.effective_date    = $eff_date,
                    v.law_type          = $law_type,
                    v.mst               = $mst,
                    v.file_path         = $file_path
                """,
                {
                    "law_name":  law_name,
                    "vkey":      vkey,
                    "pdate":     v["pdate"],
                    "pno":       v["pno"],
                    "eff_date":  v.get("eff_date", ""),
                    "law_type":  v.get("law_type", ""),
                    "mst":       v.get("mst", ""),
                    "file_path": v.get("file", ""),
                },
            )
            created += 1

    return created, existing


def build_version_index(out_dir: Path) -> dict[str, dict]:
    """promulgation_no → 버전 정보 인덱스 파일을 law/decree/rule 각 서브폴더에 생성"""
    results = {}
    for subdir in ("law", "decree", "rule"):
        sub_path = out_dir / subdir
        if not sub_path.exists():
            continue
        versions = load_versions_from_dir(out_dir, subdir)
        if not versions:
            continue

        index = {}
        for v in versions:
            pno = str(v["pno"]).lstrip("0")
            index[pno] = {
                "version_key": f"{v['pdate']}_{v['pno']}",
                "pdate":    v["pdate"],
                "pno":      v["pno"],
                "eff_date": v.get("eff_date", ""),
                "law_name": v.get("law_name", ""),
                "mst":      v.get("mst", ""),
                "file":     v.get("file", ""),  # 조문 추출용
            }

        idx_file = sub_path / "_version_index.json"
        idx_file.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [{subdir}] 인덱스: {idx_file.name} ({len(index)}개 버전)")
        results[subdir] = index

    return results


# ─────────────────────────────────────────────────────────
# 5. 버전 조회 유틸 (statute_version.py에서 사용)
# ─────────────────────────────────────────────────────────

def lookup_law_version_local(law_slug: str, promulgation_no: str) -> dict | None:
    """
    로컬 _version_index.json에서 해당 공포번호 이전 버전 반환.
    (Neo4j 없이도 동작하는 경량 조회)
    """
    idx_file = LAW_DIR / law_slug / "_version_index.json"
    if not idx_file.exists():
        return None

    index = json.loads(idx_file.read_text(encoding="utf-8"))
    pno_stripped = promulgation_no.lstrip("0")

    # 해당 공포번호의 버전 찾기
    target = index.get(pno_stripped)
    if not target:
        return None

    # 날짜 기준 정렬된 버전 목록
    all_versions = sorted(index.values(), key=lambda x: x["pdate"])

    # target 이전 버전 찾기
    enacted_date = target["pdate"]
    prior = [v for v in all_versions if v["pdate"] < enacted_date]
    if not prior:
        return None

    return prior[-1]  # 가장 최근의 이전 버전


# ─────────────────────────────────────────────────────────
# 6. 메인
# ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true", help="API에서 다운로드")
    parser.add_argument("--ingest",   action="store_true", help="Neo4j 삽입")
    parser.add_argument("--index",    action="store_true", help="로컬 인덱스 파일 생성")
    parser.add_argument("--all",      action="store_true", help="download + index + ingest")
    parser.add_argument("--law",      type=str, default=None, help="특정 법령만 처리")
    args = parser.parse_args()

    if not (args.download or args.ingest or args.index or args.all):
        parser.print_help()
        return

    target_laws = LAWS
    if args.law:
        target_laws = [l for l in LAWS if args.law in l["name"]]
        if not target_laws:
            print(f"[ERR] '{args.law}'에 해당하는 법령 없음")
            return

    do_download = args.download or args.all
    do_index    = args.index or args.all
    do_ingest   = args.ingest or args.all

    driver = None
    if do_ingest:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
        )

    for law_info in target_laws:
        name = law_info["name"]
        slug = law_info["slug"]
        out_dir = LAW_DIR / slug

        print(f"\n{'='*60}")
        print(f"처리 중: {name} (slug={slug})")
        print(f"{'='*60}")

        if do_download:
            download_law(law_info)

        if do_index and out_dir.exists():
            print(f"\n[{name}] 버전 인덱스 생성...")
            build_version_index(out_dir)

        if do_ingest and driver and out_dir.exists():
            print(f"\n[{name}] Neo4j 삽입 중...")
            versions = load_versions_from_dir(out_dir)
            created, existing = ingest_law_versions(versions, name, driver)
            print(f"  완료: 신규 {created}개 / 기존 {existing}개")

    if driver:
        driver.close()

    print("\n\n=== 전체 완료 ===")


if __name__ == "__main__":
    main()
