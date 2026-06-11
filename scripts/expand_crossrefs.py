"""
CrossRef 확장 파이프라인

1. cache/ 폴더에서 모든 EXTERNAL CrossRef 타겟 수집
2. 타겟 문자열에서 법령명 파싱 (예: "소득세법 제65조제1항" → "소득세법")
3. law/ 폴더에 없는 법령 자동 다운로드 (DRF API)
4. 버전 인덱스 빌드
5. 최신 버전 LAW_7 파이프라인 실행 → Neo4j 인제스트

실행:
  # 어떤 법령이 참조되는지만 확인
  python -m scripts.expand_crossrefs --scan-only

  # 다운로드 + 인제스트 전체 자동
  python -m scripts.expand_crossrefs --run
"""
from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests
import urllib3
urllib3.disable_warnings()

sys.stdout.reconfigure(encoding="utf-8")

ROOT     = Path(__file__).parent.parent
CACHE    = ROOT / "cache"
LAW_DIR  = ROOT / "law"
OC       = "seungmi0723"
BASE_URL = "http://www.law.go.kr/DRF"
HEADERS  = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# ── 이미 law/ 에 있는 법령명 목록 ────────────────────────────────────────────
EXISTING_SLUGS = {
    "국세기본법":       ("gukse_basic",      ["law", "decree"]),
    "국세기본법 시행령": ("gukse_basic",      ["decree"]),
    "국세기본법 시행규칙": ("gukse_basic",   ["rule"]),
    "국세징수법":       ("gukse_collection", ["law", "decree", "rule"]),
    "국세징수법 시행령": ("gukse_collection", ["decree"]),
    "국세징수법 시행규칙": ("gukse_collection", ["rule"]),
    "법인세법":         ("corporate_tax",    ["law", "decree", "rule"]),
    "법인세법 시행령":   ("corporate_tax",   ["decree"]),
    "법인세법 시행규칙": ("corporate_tax",   ["rule"]),
    "소득세법":         ("income_tax",       ["law", "decree", "rule"]),
    "소득세법 시행령":   ("income_tax",      ["decree"]),
    "소득세법 시행규칙": ("income_tax",      ["rule"]),
    "부가가치세법":     ("vat",              ["law", "decree", "rule"]),
    "부가가치세법 시행령": ("vat",           ["decree"]),
    "부가가치세법 시행규칙": ("vat",         ["rule"]),
    "조세범처벌법":     ("tax_crime",        ["law"]),
    "조세범처벌절차법": ("tax_crime_proc",   ["law", "decree"]),
    "조세범처벌절차법 시행령": ("tax_crime_proc", ["decree"]),
    "국제조세조정에 관한 법률": ("itcl",    ["law", "decree", "rule"]),
    "국제조세조정에관한법률": ("itcl",      ["law", "decree", "rule"]),
}


# ── 1. CrossRef 타겟 수집 ─────────────────────────────────────────────────────

def collect_external_targets() -> dict[str, int]:
    """cache/ 폴더 전체를 스캔해 EXTERNAL 타겟 → 빈도 딕셔너리 반환."""
    counts: dict[str, int] = {}
    for law_dir in CACHE.iterdir():
        if not law_dir.is_dir():
            continue
        for ver_dir in law_dir.iterdir():
            if not ver_dir.is_dir():
                continue
            cr_dir = ver_dir / "cross_refs"
            if not cr_dir.exists():
                continue
            for f in cr_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    for ref in data.get("cross_refs", []):
                        if ref.get("type") == "EXTERNAL":
                            t = (ref.get("target") or "").strip()
                            if t:
                                counts[t] = counts.get(t, 0) + 1
                except Exception:
                    pass
    return counts


# ── 2. 타겟 문자열 → 법령명 파싱 ─────────────────────────────────────────────

_LAW_NAME_RE = re.compile(
    r'^(.+?)\s+제\s*\d+\s*조',
    re.UNICODE,
)
_JOSA = re.compile(r'(에서|에|의|이|가|을|를|은|는|과|와|로|으로|부터)$')


def parse_law_name(target: str) -> str | None:
    """
    "소득세법 제65조제1항"  → "소득세법"
    "법인세법 시행령 제89조" → "법인세법 시행령"
    "제22조제2항"            → None (내부 참조)
    """
    target = target.strip()
    # 내부 참조 (법령명 없이 바로 제X조로 시작)
    if re.match(r'^제\s*\d+', target):
        return None
    m = _LAW_NAME_RE.match(target)
    if not m:
        return None
    name = m.group(1).strip()
    # 조사 제거
    name = _JOSA.sub("", name).strip()
    # 빈 문자열 or 너무 짧은 것 제거
    if len(name) < 2:
        return None
    return name


def law_name_to_slug(name: str) -> str:
    """
    "조세특례제한법 시행령" → "joseteukrejehan_decree"
    일단 한글 법령명을 기반으로 slug 생성.
    """
    # 공백·특수문자 → _
    slug = re.sub(r'\s+', '_', name.strip())
    slug = re.sub(r'[^\w]', '', slug, flags=re.UNICODE)
    # 한글 → 영문 변환이 어려우므로 그냥 한글 slug 사용 (폴더명에 한글 허용)
    return slug.lower()


def law_name_kind(name: str) -> str:
    """법령명 → law / decree / rule"""
    if "시행규칙" in name:
        return "rule"
    if "시행령" in name:
        return "decree"
    return "law"


def base_law_name(name: str) -> str:
    """'법인세법 시행령' → '법인세법'"""
    for suffix in [" 시행규칙", " 시행령"]:
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return name


# ── 3. DRF 다운로드 ──────────────────────────────────────────────────────────

def _fetch_mst_list_by_name(law_name: str) -> list[tuple[str, str]]:
    """lsHistory 에서 (MST, 실제법령명) 목록 반환."""
    msts = []
    page = 1
    while True:
        try:
            sess = requests.Session()
            sess.verify = False
            resp = sess.get(
                f"{BASE_URL}/lawSearch.do",
                params={"OC": OC, "target": "lsHistory", "type": "HTML",
                        "query": law_name, "display": 100, "page": page},
                headers=HEADERS, timeout=15,
            )
            html = resp.text
        except Exception as e:
            print(f"    [ERR] lsHistory 요청 실패: {e}")
            break

        rows = re.findall(r'MST=(\d+)[^"]*"[^>]*>([^<]+)</a>', html)
        if not rows:
            break

        # 검색어가 법령명에 포함되는 것만
        matched = [(mst, nm.strip()) for mst, nm in rows if law_name in nm.strip()]
        if not matched:
            break
        msts.extend(matched)

        if len(matched) < 100:
            break
        page += 1
        time.sleep(0.3)
    return msts


def _fetch_law_json(mst: str) -> dict | None:
    for attempt in range(3):
        try:
            sess = requests.Session()
            sess.verify = False
            resp = sess.get(
                f"{BASE_URL}/lawService.do",
                params={"OC": OC, "target": "law", "MST": mst, "type": "JSON"},
                headers=HEADERS, timeout=20,
            )
            if resp.status_code == 200 and len(resp.text) > 100:
                return resp.json()
        except Exception:
            if attempt < 2:
                time.sleep(1 + attempt)
    return None


def _extract_meta(data: dict) -> dict | None:
    if not data:
        return None
    root = data.get(next(iter(data), ""), {})
    info = root.get("기본정보", {})
    if not info:
        return None
    law_type = info.get("법종구분", "")
    if isinstance(law_type, dict):
        law_type = law_type.get("content", "")
    pno   = str(info.get("공포번호", "")).strip()
    pdate = str(info.get("공포일자", "")).strip()
    if not (pdate and pno):
        return None
    mst_val = info.get("법령MST") or info.get("법령키") or ""
    return {
        "law_name": (info.get("법령명_한글") or "").strip(),
        "pdate": pdate, "pno": pno,
        "eff_date": str(info.get("시행일자", "")).strip(),
        "law_type": str(law_type).strip(),
        "mst": str(mst_val),
        "file": f"MST_{mst_val}.json",
    }


def download_new_law(law_name: str, kind: str, slug: str) -> Path | None:
    """
    새 법령 다운로드 → law/{slug}/{kind}/ 에 저장.
    현재 버전(가장 최신 pdate) 만 저장하고 버전 인덱스 빌드.
    반환: 저장된 가장 최신 파일 경로 (없으면 None)
    """
    out_dir = LAW_DIR / slug / kind
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"  📥 [{law_name}] MST 목록 수집...")
    mst_rows = _fetch_mst_list_by_name(law_name)
    if not mst_rows:
        print(f"  ⚠️  MST 없음: {law_name}")
        return None

    print(f"  → {len(mst_rows)}개 MST 발견, 다운로드 중...")
    index: dict[str, dict] = {}
    latest_path = None
    latest_pdate = ""

    for mst, nm in mst_rows:
        # 법/령/규칙 분류
        if "시행규칙" in nm and kind != "rule":
            continue
        if "시행령" in nm and "시행규칙" not in nm and kind != "decree":
            continue
        if "시행령" not in nm and "시행규칙" not in nm and kind != "law":
            continue

        save_path = out_dir / f"MST_{mst}.json"
        if save_path.exists():
            meta = _extract_meta(json.loads(save_path.read_text(encoding="utf-8")))
        else:
            data = _fetch_law_json(mst)
            if not data:
                continue
            save_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            meta = _extract_meta(data)
            time.sleep(0.2)

        if not meta:
            continue

        pno_stripped = meta["pno"].lstrip("0") or "0"
        index[pno_stripped] = {
            "version_key": f"{meta['pdate']}_{meta['pno']}",
            "pdate": meta["pdate"],
            "pno":   meta["pno"],
            "eff_date": meta["eff_date"],
            "law_name": meta["law_name"] or law_name,
            "mst": meta["mst"],
            "file": f"MST_{mst}.json",
        }
        if meta["pdate"] > latest_pdate:
            latest_pdate = meta["pdate"]
            latest_path  = save_path

    # 버전 인덱스 저장
    idx_path = out_dir / "_version_index.json"
    idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✅ {len(index)}개 버전 저장 → {out_dir.relative_to(ROOT)}")
    return latest_path


# ── 4. 메인 ──────────────────────────────────────────────────────────────────

def run(dry_run: bool = False) -> None:
    import dotenv, os
    dotenv.load_dotenv()

    print("=== CrossRef 외부 참조 법령 수집 ===")
    targets = collect_external_targets()
    print(f"  EXTERNAL 참조 {len(targets)}건")

    # 법령명 파싱
    law_freq: dict[str, int] = {}
    for t, cnt in targets.items():
        nm = parse_law_name(t)
        if nm:
            law_freq[nm] = law_freq.get(nm, 0) + cnt

    # 기존 보유 법령 제거
    new_laws: dict[str, int] = {}
    for nm, cnt in sorted(law_freq.items(), key=lambda x: -x[1]):
        if nm not in EXISTING_SLUGS:
            new_laws[nm] = cnt

    print(f"\n=== 미보유 참조 법령 ({len(new_laws)}개) ===")
    for nm, cnt in sorted(new_laws.items(), key=lambda x: -x[1]):
        print(f"  {nm:30s}  참조 {cnt}회")

    if dry_run:
        print("\n(--scan-only 모드: 다운로드 생략)")
        return

    # 중복 제거: "법인세법 시행령" → base = "법인세법", kind = "decree"
    # slug는 base_law_name 기준으로 생성
    processed_slugs: set[str] = set()
    to_process: list[tuple[str, str, str]] = []  # (law_name_base, kind, slug)

    for nm in sorted(new_laws, key=lambda x: -new_laws[x]):
        kind = law_name_kind(nm)
        base = base_law_name(nm)
        slug = law_name_to_slug(base)
        to_process.append((nm, kind, slug))

    print(f"\n=== 다운로드 + 인제스트 시작 ({len(to_process)}개) ===")

    from LAW_7.pipeline import run_single_pipeline

    for law_name, kind, slug in to_process:
        print(f"\n{'─'*60}")
        print(f"▶ {law_name}  [kind={kind}, slug={slug}]")

        mst_path = download_new_law(law_name, kind, slug)
        if not mst_path:
            print(f"  ⏭️  다운로드 실패, skip")
            continue

        try:
            print(f"  🔄 파이프라인 실행: {mst_path.name}")
            run_single_pipeline(mst_path, slug)
            print(f"  ✅ 완료")
        except Exception as e:
            print(f"  ❌ 파이프라인 오류: {e}")

    print("\n🎉 CrossRef 확장 완료")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan-only", action="store_true", help="다운로드 없이 참조 법령명만 출력")
    ap.add_argument("--run",       action="store_true", help="다운로드 + 인제스트 전체 실행")
    args = ap.parse_args()

    if args.scan_only:
        run(dry_run=True)
    elif args.run:
        run(dry_run=False)
    else:
        ap.print_help()
