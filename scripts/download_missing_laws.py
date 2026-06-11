"""
미보유 참조 법령 다운로드 전용 (LLM/Neo4j 없음)
law/{slug}/{kind}/MST_*.json + _version_index.json 생성

실행:
  python -m scripts.download_missing_laws
"""
from __future__ import annotations

import json, re, sys, time
from pathlib import Path

import requests, urllib3
urllib3.disable_warnings()

sys.stdout.reconfigure(encoding="utf-8")

ROOT    = Path(__file__).parent.parent
LAW_DIR = ROOT / "law"
OC      = "seungmi0723"
BASE    = "http://www.law.go.kr/DRF"
HDR     = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# 다운로드 대상 (name, slug, kind)
TARGETS = [
    # 조세특례제한법 (193건 + 31건)
    ("조세특례제한법",       "joseteukrejehan",  "law"),
    ("조세특례제한법 시행령", "joseteukrejehan",  "decree"),
    ("조세특례제한법 시행규칙", "joseteukrejehan", "rule"),
    # 상속세 및 증여세법 (116건 + 36건)
    ("상속세 및 증여세법",       "inheritance_tax",  "law"),
    ("상속세 및 증여세법 시행령", "inheritance_tax",  "decree"),
    ("상속세 및 증여세법 시행규칙", "inheritance_tax", "rule"),
    # 자본시장과 금융투자업에 관한 법률 (123건 + 15건)
    ("자본시장과 금융투자업에 관한 법률",       "capital_market",  "law"),
    ("자본시장과 금융투자업에 관한 법률 시행령", "capital_market",  "decree"),
    ("자본시장과 금융투자업에 관한 법률 시행규칙", "capital_market", "rule"),
    # 관세법 (37건)
    ("관세법",       "customs",  "law"),
    ("관세법 시행령", "customs",  "decree"),
    ("관세법 시행규칙", "customs", "rule"),
    # 개별소비세법 (18건)
    ("개별소비세법",       "individual_consumption", "law"),
    ("개별소비세법 시행령", "individual_consumption", "decree"),
    # 종합부동산세법 (10건)
    ("종합부동산세법",       "comprehensive_realty", "law"),
    ("종합부동산세법 시행령", "comprehensive_realty", "decree"),
]


def _fetch_mst_list(law_name: str) -> list[str]:
    msts, page = [], 1
    while True:
        try:
            s = requests.Session(); s.verify = False
            r = s.get(f"{BASE}/lawSearch.do",
                      params={"OC": OC, "target": "lsHistory", "type": "HTML",
                              "query": law_name, "display": 100, "page": page},
                      headers=HDR, timeout=15)
            rows = re.findall(r'MST=(\d+)[^"]*"[^>]*>([^<]+)</a>', r.text)
            matched = [mst for mst, nm in rows if law_name in nm.strip()]
            if not matched: break
            msts.extend(matched)
            if len(matched) < 100: break
            page += 1; time.sleep(0.3)
        except Exception as e:
            print(f"  [ERR] MST 목록: {e}"); break
    return msts


def _fetch_json(mst: str) -> dict | None:
    for i in range(3):
        try:
            s = requests.Session(); s.verify = False
            r = s.get(f"{BASE}/lawService.do",
                      params={"OC": OC, "target": "law", "MST": mst, "type": "JSON"},
                      headers=HDR, timeout=20)
            if r.status_code == 200 and len(r.text) > 100:
                return r.json()
        except Exception:
            if i < 2: time.sleep(1 + i)
    return None


def _extract_meta(data: dict) -> dict | None:
    try:
        root = data.get(next(iter(data)), {})
        info = root.get("기본정보", {})
        pno   = str(info.get("공포번호", "")).strip()
        pdate = str(info.get("공포일자", "")).strip()
        if not (pno and pdate): return None
        law_type = info.get("법종구분", "")
        if isinstance(law_type, dict): law_type = law_type.get("content", "")
        law_id = str(info.get("법령ID") or "").strip()
        return {
            "pno": pno, "pdate": pdate,
            "eff_date": str(info.get("시행일자", "")).strip(),
            "law_name": str(info.get("법령명_한글") or "").strip(),
            "mst": str(info.get("법령MST") or info.get("법령키") or "").strip(),
            "law_id": law_id,
        }
    except Exception:
        return None


def download_one(law_name: str, slug: str, kind: str) -> int:
    out_dir = LAW_DIR / slug / kind
    idx_path = out_dir / "_version_index.json"

    # 이미 인덱스 있으면 스킵
    if idx_path.exists():
        existing = json.loads(idx_path.read_text(encoding="utf-8"))
        if existing:
            print(f"  [SKIP] {law_name} — 이미 {len(existing)}개 버전 존재")
            return len(existing)

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"  📥 {law_name} → {out_dir.relative_to(ROOT)}")

    mst_list = _fetch_mst_list(law_name)
    if not mst_list:
        print(f"  ⚠️  MST 없음 — 이 법령명으로 DRF에서 찾지 못함")
        return 0

    print(f"     MST {len(mst_list)}개 발견, 다운로드 중...")
    index: dict[str, dict] = {}

    for mst in mst_list:
        fp = out_dir / f"MST_{mst}.json"
        if fp.exists():
            data = json.loads(fp.read_text(encoding="utf-8"))
        else:
            data = _fetch_json(mst)
            if not data: continue
            fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            time.sleep(0.15)

        meta = _extract_meta(data)
        if not meta: continue

        # kind 분류 확인
        nm = meta["law_name"]
        is_rule   = "시행규칙" in nm
        is_decree = "시행령" in nm and not is_rule
        is_law    = not is_rule and not is_decree
        if kind == "rule"   and not is_rule:   continue
        if kind == "decree" and not is_decree: continue
        if kind == "law"    and not is_law:    continue

        pno_key = meta["pno"].lstrip("0") or "0"
        index[pno_key] = {
            "version_key": f"{meta['pdate']}_{meta['pno']}",
            "pdate":    meta["pdate"],
            "pno":      meta["pno"],
            "eff_date": meta["eff_date"],
            "law_name": meta["law_name"],
            "mst":      meta["mst"],
            "file":     f"MST_{mst}.json",
            "law_id":   meta["law_id"],
        }

    idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    if index:
        dates = sorted(v["pdate"] for v in index.values())
        print(f"     ✅ {len(index)}개 버전 ({dates[0]}~{dates[-1]}) 저장")
    else:
        print(f"     ⚠️  해당 kind 버전 없음 (kind={kind})")
    return len(index)


def main():
    print("=== 미보유 참조 법령 다운로드 ===\n")
    for law_name, slug, kind in TARGETS:
        download_one(law_name, slug, kind)
    print("\n✅ 완료")


if __name__ == "__main__":
    main()
