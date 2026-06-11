"""
법령 새 버전 감지 — 법제처 DRF API vs 로컬 _version_index.json 비교

실행:
    python -m RISK.monitor               # 8개 세법 전체 체크
    python -m RISK.monitor --law 법인세법  # 특정 법령만
    python -m RISK.monitor --auto        # 새 버전 발견 시 자동 분석 실행

DRF API (CLAUDE.md 기준):
    GET http://www.law.go.kr/DRF/lawSearch.do
        ?OC=seungmi0723&target=lsHistory&type=HTML&query={법령명}&display=100&page=1
    → HTML 파싱으로 공포번호(MST) 목록 수집

    GET http://www.law.go.kr/DRF/lawService.do
        ?OC=seungmi0723&target=law&MST={mst}&type=JSON
    → 개별 버전 JSON 다운로드
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Optional

import requests
import urllib3

urllib3.disable_warnings()

ROOT = Path(__file__).parent.parent
LAW_DIR = ROOT / "law"

OC = "seungmi0723"
SEARCH_URL = "http://www.law.go.kr/DRF/lawSearch.do"
SERVICE_URL = "http://www.law.go.kr/DRF/lawService.do"

LAW_SLUGS: dict[str, str] = {
    # 핵심 세법
    "국세기본법": "gukse_basic",
    "국세징수법": "gukse_collection",
    "법인세법": "corporate_tax",
    "소득세법": "income_tax",
    "부가가치세법": "vat",
    "조세범처벌법": "tax_crime",
    "조세범처벌절차법": "tax_crime_proc",
    "국제조세조정에 관한 법률": "itcl",
    # 외부 참조 법령 (세법 연동)
    "조세특례제한법": "joseteukrejehan",
    "상속세 및 증여세법": "inheritance_tax",
    "관세법": "customs",
    "종합부동산세법": "comprehensive_realty",
    "개별소비세법": "individual_consumption",
    "자본시장과 금융투자업에 관한 법률": "capital_market",
}

KIND_FOLDER: dict[str, str] = {
    "LAW": "law",
    "DECREE": "decree",
    "RULE": "rule",
}

KIND_TARGET: dict[str, str] = {
    "LAW": "law",
    "DECREE": "admrul",
    "RULE": "admrule",
}


# ── DRF API 조회 ─────────────────────────────────────────────────────────────

def _fetch_history_html(law_name: str) -> str:
    """법령 이력 HTML 반환 — 요청마다 새 Session (ConnectionResetError 방지)."""
    sess = requests.Session()
    resp = sess.get(
        SEARCH_URL,
        params={
            "OC": OC,
            "target": "lsHistory",
            "type": "HTML",
            "query": law_name,
            "display": 100,
            "page": 1,
        },
        timeout=20,
        verify=False,
    )
    resp.raise_for_status()
    return resp.text


def _parse_mst_list(html: str) -> list[dict]:
    """
    HTML에서 MST번호, 공포일자, 공포번호 추출.
    반환: [{"mst": "...", "pdate": "YYYYMMDD", "pno": "NNNNNNN"}, ...]
    """
    results = []
    # MST 링크 패턴: lawService.do?...MST=12345678...
    for m in re.finditer(r"MST=(\d+)", html):
        mst = m.group(1)
        # 같은 MST 중복 방지
        if any(r["mst"] == mst for r in results):
            continue
        results.append({"mst": mst, "pdate": "", "pno": ""})

    # 공포일자·번호는 별도 패턴 — 없으면 빈 값으로 유지 (다운로드 후 JSON에서 읽음)
    return results


def fetch_remote_mst_list(law_name: str) -> list[str]:
    """법제처에서 법령명으로 MST 번호 목록 수집."""
    html = _fetch_history_html(law_name)
    items = _parse_mst_list(html)
    return [it["mst"] for it in items]


def download_law_version_json(mst: str, kind: str = "law") -> Optional[dict]:
    """MST 번호로 법령 버전 JSON 다운로드."""
    sess = requests.Session()
    resp = sess.get(
        SERVICE_URL,
        params={"OC": OC, "target": KIND_TARGET.get(kind, "law"), "MST": mst, "type": "JSON"},
        timeout=30,
        verify=False,
    )
    if resp.status_code != 200:
        return None
    try:
        return resp.json()
    except Exception:
        return None


# ── 로컬 인덱스 조회 ─────────────────────────────────────────────────────────

def _load_local_index(law_name: str, kind: str) -> dict:
    slug = LAW_SLUGS.get(law_name, "")
    folder = KIND_FOLDER.get(kind, "law")
    idx_path = LAW_DIR / slug / folder / "_version_index.json"
    if not idx_path.exists():
        return {}
    with idx_path.open(encoding="utf-8") as f:
        return json.load(f)


def _get_local_mst_set(law_name: str, kind: str) -> set[str]:
    """로컬에 있는 MST 번호 집합."""
    index = _load_local_index(law_name, kind)
    msts = set()
    for entry in index.values():
        mst = entry.get("mst", "")
        if mst:
            msts.add(str(mst))
    return msts


# ── 새 버전 감지 ─────────────────────────────────────────────────────────────

def check_new_versions(law_name: str, kind: str = "LAW") -> list[str]:
    """
    법제처 원격 MST 목록 vs 로컬 인덱스 비교.
    로컬에 없는 MST 번호 목록 반환 (= 새 버전).
    """
    try:
        remote_msts = set(fetch_remote_mst_list(law_name))
    except Exception as e:
        print(f"  [경고] {law_name} DRF 조회 실패: {e}")
        return []

    local_msts = _get_local_mst_set(law_name, kind)
    new_msts = remote_msts - local_msts
    return sorted(new_msts)


def poll_all_laws(kinds: list[str] = ("LAW",)) -> dict[str, list[str]]:
    """
    8개 세법 × kind 조합으로 새 버전 감지.
    반환: { "법인세법/LAW": ["MST1", "MST2"], ... }
    """
    results: dict[str, list[str]] = {}

    for law_name in LAW_SLUGS:
        for kind in kinds:
            key = f"{law_name}/{kind}"
            print(f"  체크 중: {key} ...", end=" ", flush=True)

            # RULE이 없는 법령은 스킵
            slug = LAW_SLUGS[law_name]
            folder = KIND_FOLDER[kind]
            idx_path = LAW_DIR / slug / folder / "_version_index.json"
            if not idx_path.exists():
                print("(인덱스 없음, 스킵)")
                continue

            new_msts = check_new_versions(law_name, kind)
            if new_msts:
                print(f"새 버전 {len(new_msts)}개: {new_msts}")
                results[key] = new_msts
            else:
                print("최신")

            time.sleep(0.5)  # DRF API 부하 방지

    return results


# ── 새 버전 자동 다운로드 ───────────────────────────────────────────────────

def download_and_register(
    law_name: str,
    kind: str,
    mst: str,
) -> Optional[Path]:
    """
    새 MST를 다운로드하고 law/{slug}/{folder}/ 에 저장.
    _version_index.json 갱신은 scripts/build_law_index_only.py에 위임.
    """
    slug = LAW_SLUGS.get(law_name, "")
    folder = KIND_FOLDER.get(kind, "law")
    if not slug:
        return None

    data = download_law_version_json(mst, kind)
    if not data:
        print(f"  [경고] MST={mst} 다운로드 실패")
        return None

    out_dir = LAW_DIR / slug / folder
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"MST_{mst}.json"
    out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  저장: {out_file}")
    return out_file


# ── 자동 분석 실행 ───────────────────────────────────────────────────────────

def auto_analyze_new_versions(new_by_law: dict[str, list[str]]) -> None:
    """새 버전 발견 시 컨설팅 파이프라인 자동 실행."""
    if not new_by_law:
        print("새 버전 없음 — 분석 스킵")
        return

    from RISK.consulting import run_full_analysis

    for key, msts in new_by_law.items():
        law_name, kind = key.split("/")
        print(f"\n=== {key} 자동 분석 ({len(msts)}개 새 버전) ===")

        for mst in msts:
            # 다운로드
            saved = download_and_register(law_name, kind, mst)
            if not saved:
                continue

            # 인덱스 갱신 (subprocess 호출)
            import subprocess, sys
            subprocess.run(
                [sys.executable, "scripts/build_law_index_only.py", "--law", law_name],
                cwd=str(ROOT),
                check=False,
            )

            # 최신 버전으로 분석 실행
            try:
                result = run_full_analysis(law_name, kind)
                print(f"  ✅ 분석 완료 — priority={result.consulting.overall_priority}")
            except Exception as e:
                print(f"  [오류] 분석 실패: {e}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="법령 새 버전 감지 + 자동 분석")
    ap.add_argument("--law", help="특정 법령명만 체크 (기본: 전체)")
    ap.add_argument("--kind", default="LAW", choices=["LAW", "DECREE", "RULE"])
    ap.add_argument("--auto", action="store_true", help="새 버전 발견 시 자동 분석")
    args = ap.parse_args()

    print("=== 법령 새 버전 감지 ===\n")

    if args.law:
        new_msts = check_new_versions(args.law, args.kind)
        if new_msts:
            print(f"새 버전 {len(new_msts)}개: {new_msts}")
            if args.auto:
                auto_analyze_new_versions({f"{args.law}/{args.kind}": new_msts})
        else:
            print(f"{args.law}/{args.kind}: 최신 상태")
    else:
        new_by_law = poll_all_laws(kinds=["LAW", "DECREE", "RULE"])
        print(f"\n감지 완료 — 새 버전 있는 법령: {len(new_by_law)}개")
        if args.auto:
            auto_analyze_new_versions(new_by_law)


if __name__ == "__main__":
    main()
