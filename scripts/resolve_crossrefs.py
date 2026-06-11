"""
CrossRef Resolution — 로컬 JSON 파일 기반, Neo4j 노드 추가 없음

흐름:
  1. Neo4j에서 resolved_version_key 없는 LawTarget 전체 로드
  2. citing LawVersion.effective_date 확인
  3. target 파싱 → {law_name, art_no, para_no, item_no, subitem_no}
  4. law/_version_index.json에서 effective_date 기준 최신 버전 찾기 (로컬)
  5. MST_*.json 파싱 → 조/항/호/목 텍스트 직접 추출 (로컬)
  6. LawTarget 노드 속성 업데이트 (새 노드 0개)

실행:
  python -m scripts.resolve_crossrefs --dry-run
  python -m scripts.resolve_crossrefs --run
"""
from __future__ import annotations

import json, os, re, sys
from collections import defaultdict
from pathlib import Path

import dotenv
dotenv.load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

from neo4j import GraphDatabase

URI  = os.getenv("NEO4J_URI")
AUTH = (os.getenv("NEO4J_USERNAME", "neo4j"), os.getenv("NEO4J_PASSWORD"))
driver = GraphDatabase.driver(URI, auth=AUTH)

ROOT    = Path(__file__).parent.parent
LAW_DIR = ROOT / "law"

# ── law_id → 법령명 캐시 (로컬 MST JSON에서 빌드) ────────────────────────────

_LAW_ID_NAME_CACHE: dict[str, str] = {}  # law_id(str) → 법령명

def _build_law_id_cache() -> None:
    """slug/kind별 최신 MST JSON 1개씩 읽어 law_id → 법령명 매핑 구성."""
    for slug_dir in LAW_DIR.iterdir():
        if not slug_dir.is_dir():
            continue
        for kind_dir in slug_dir.iterdir():
            if not kind_dir.is_dir():
                continue
            idx_path = kind_dir / "_version_index.json"
            if not idx_path.exists():
                continue
            try:
                idx = json.loads(idx_path.read_text(encoding="utf-8"))
                if not idx:
                    continue
                latest_pno = max(idx, key=lambda k: idx[k].get("pdate", "0"))
                mst_file = idx[latest_pno].get("file")
                if not mst_file:
                    continue
                raw = json.loads((kind_dir / mst_file).read_text(encoding="utf-8"))
                meta = raw["법령"]["기본정보"]
                law_id = meta.get("법령ID")
                law_name = meta.get("법령명_한글")
                if law_id and law_name:
                    _LAW_ID_NAME_CACHE[str(law_id)] = law_name
            except Exception:
                pass

# ── 법령명 → (slug, kind) 매핑 ───────────────────────────────────────────────

_NAME_TO_SLUG: dict[str, tuple[str, str]] = {
    "국세기본법":           ("gukse_basic",      "law"),
    "국세기본법 시행령":     ("gukse_basic",      "decree"),
    "국세기본법 시행규칙":   ("gukse_basic",      "rule"),
    "국세징수법":           ("gukse_collection", "law"),
    "국세징수법 시행령":     ("gukse_collection", "decree"),
    "국세징수법 시행규칙":   ("gukse_collection", "rule"),
    "법인세법":             ("corporate_tax",    "law"),
    "법인세법 시행령":       ("corporate_tax",    "decree"),
    "법인세법 시행규칙":     ("corporate_tax",    "rule"),
    "소득세법":             ("income_tax",       "law"),
    "소득세법 시행령":       ("income_tax",       "decree"),
    "소득세법 시행규칙":     ("income_tax",       "rule"),
    "부가가치세법":         ("vat",              "law"),
    "부가가치세법 시행령":   ("vat",              "decree"),
    "부가가치세법 시행규칙": ("vat",              "rule"),
    "조세범처벌법":         ("tax_crime",        "law"),
    "조세범 처벌법":        ("tax_crime",        "law"),
    "조세범처벌절차법":     ("tax_crime_proc",   "law"),
    "조세범처벌절차법 시행령": ("tax_crime_proc", "decree"),
    "국제조세조정에 관한 법률": ("itcl",          "law"),
    "국제조세조정에관한법률": ("itcl",            "law"),
    "국제조세조정에 관한 법률 시행령": ("itcl",   "decree"),
    "국제조세조정에 관한 법률 시행규칙": ("itcl", "rule"),
    # 확장 법령 (download_missing_laws.py 로 다운로드)
    "조세특례제한법":             ("joseteukrejehan",       "law"),
    "조세특례제한법 시행령":       ("joseteukrejehan",       "decree"),
    "조세특례제한법 시행규칙":     ("joseteukrejehan",       "rule"),
    "상속세 및 증여세법":          ("inheritance_tax",       "law"),
    "상속세및증여세법":            ("inheritance_tax",       "law"),
    "상속세 및 증여세법 시행령":   ("inheritance_tax",       "decree"),
    "상속세 및 증여세법 시행규칙": ("inheritance_tax",       "rule"),
    "자본시장과 금융투자업에 관한 법률":           ("capital_market",  "law"),
    "자본시장과금융투자업에관한법률":              ("capital_market",  "law"),
    "자본시장과 금융투자업에 관한 법률 시행령":   ("capital_market",  "decree"),
    "자본시장과 금융투자업에 관한 법률 시행규칙": ("capital_market",  "rule"),
    "관세법":             ("customs",               "law"),
    "관세법 시행령":       ("customs",               "decree"),
    "관세법 시행규칙":     ("customs",               "rule"),
    "개별소비세법":       ("individual_consumption", "law"),
    "개별소비세법 시행령": ("individual_consumption", "decree"),
    "종합부동산세법":       ("comprehensive_realty",  "law"),
    "종합부동산세법 시행령": ("comprehensive_realty",  "decree"),
}

# 접미사 기반 fallback
def _infer_slug_kind(name: str) -> tuple[str, str] | None:
    if name in _NAME_TO_SLUG:
        return _NAME_TO_SLUG[name]
    if name.endswith("시행규칙"):
        base = name[:-len("시행규칙")].strip()
        for k, v in _NAME_TO_SLUG.items():
            if k == base:
                return (v[0], "rule")
    if name.endswith("시행령"):
        base = name[:-len("시행령")].strip()
        for k, v in _NAME_TO_SLUG.items():
            if k == base:
                return (v[0], "decree")
    return None


# ── 버전 인덱스 캐시 ──────────────────────────────────────────────────────────

_idx_cache: dict[str, dict] = {}

def _load_index(slug: str, kind: str) -> dict | None:
    key = f"{slug}/{kind}"
    if key not in _idx_cache:
        p = LAW_DIR / slug / kind / "_version_index.json"
        if not p.exists():
            _idx_cache[key] = {}
        else:
            _idx_cache[key] = json.loads(p.read_text(encoding="utf-8"))
    return _idx_cache[key] or None


def find_version(slug: str, kind: str, eff_date: str) -> tuple[str, str] | None:
    """effective_date <= eff_date 기준 가장 최신 버전의 (version_key, mst_file) 반환."""
    idx = _load_index(slug, kind)
    if not idx:
        return None
    candidates = [
        v for v in idx.values()
        if v.get("pdate", "0") <= eff_date
    ]
    if not candidates:
        # eff_date보다 이전 버전 없으면 가장 오래된 버전 사용
        candidates = list(idx.values())
    best = max(candidates, key=lambda v: v.get("pdate", "0"))
    return best.get("version_key"), best.get("file")


# ── MST JSON 파일에서 조/항/호/목 추출 ────────────────────────────────────────

_mst_cache: dict[str, dict] = {}

def _load_mst(slug: str, kind: str, filename: str) -> dict | None:
    key = f"{slug}/{kind}/{filename}"
    if key not in _mst_cache:
        p = LAW_DIR / slug / kind / filename
        if not p.exists():
            _mst_cache[key] = {}
        else:
            _mst_cache[key] = json.loads(p.read_text(encoding="utf-8"))
    return _mst_cache[key] or None


def _norm(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return " ".join(str(x).strip() for x in v if x)
    return str(v).strip()


def _art_no_from_text(text: str) -> str | None:
    """'제65조' → '65', '제65조의2' → '65_2'"""
    m = re.search(r'제(\d+)조(?:의(\d+))?', text)
    if not m:
        return None
    return m.group(1) + (f"_{m.group(2)}" if m.group(2) else "")


def _find_article_entry(entries, art_no_target: str) -> dict | None:
    """조문단위 스트림에서 article_no 일치하는 항목 탐색."""
    for e in entries:
        text = _norm(e.get("조문내용", ""))
        no = _art_no_from_text(text)
        if no == art_no_target:
            return e
        # DRF 조문번호 fallback
        if str(e.get("조문번호", "")).lstrip("0") == art_no_target.lstrip("0"):
            if e.get("조문여부") == "조문" or re.match(r'^제\d+조', text):
                return e
    return None


def _extract_para_text(entry: dict, para_no: str) -> str | None:
    """항 내용 추출. para_no = '1', '2', ... 또는 '①', '②' ..."""
    paras = entry.get("항", [])
    if isinstance(paras, dict):
        paras = [paras]
    if not isinstance(paras, list):
        return None

    # 숫자 → 원문자 변환
    circle = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
    candidates = set()
    if para_no and para_no.isdigit():
        idx = int(para_no) - 1
        candidates.add(para_no)
        if 0 <= idx < len(circle):
            candidates.add(circle[idx])
    else:
        candidates.add(para_no)

    for p in paras:
        pno = str(p.get("항번호", "")).strip()
        if pno in candidates:
            return _norm(p.get("항내용"))
    return None


def _extract_item_text(entry: dict, para_no: str, item_no: str) -> str | None:
    """호 내용 추출. para_no가 빈 문자열이면 모든 항에서 탐색."""
    paras = entry.get("항", [])
    if isinstance(paras, dict):
        paras = [paras]

    circle = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
    para_candidates: set[str] = set()
    if para_no and para_no.isdigit():
        idx = int(para_no) - 1
        para_candidates.add(para_no)
        if 0 <= idx < len(circle):
            para_candidates.add(circle[idx])
    elif para_no:
        para_candidates.add(para_no)
    # para_no == "" → 전체 항 탐색

    for p in paras:
        pno = str(p.get("항번호", "")).strip()
        if para_candidates and pno not in para_candidates:
            continue
        items = p.get("호", [])
        if isinstance(items, dict):
            items = [items]
        for h in (items or []):
            if str(h.get("호번호", "")).strip().rstrip(".") == str(item_no):
                return _norm(h.get("호내용"))

    # 항 없이 조문 바로 아래 호가 있는 경우 (일부 법령 구조)
    direct_items = entry.get("호", [])
    if isinstance(direct_items, dict):
        direct_items = [direct_items]
    for h in (direct_items or []):
        if str(h.get("호번호", "")).strip().rstrip(".") == str(item_no):
            return _norm(h.get("호내용"))
    return None


def _extract_subitem_text(entry: dict, para_no: str, item_no: str, sub_no: str) -> str | None:
    """목 내용 추출."""
    paras = entry.get("항", [])
    if isinstance(paras, dict):
        paras = [paras]

    circle = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
    para_candidates = set()
    if para_no and para_no.isdigit():
        idx = int(para_no) - 1
        para_candidates.add(para_no)
        if 0 <= idx < len(circle):
            para_candidates.add(circle[idx])
    else:
        para_candidates.add(para_no)

    for p in paras:
        pno = str(p.get("항번호", "")).strip()
        if para_no and pno not in para_candidates:
            continue
        items = p.get("호", [])
        if isinstance(items, dict):
            items = [items]
        for h in (items or []):
            if str(h.get("호번호", "")).strip().rstrip(".") != str(item_no):
                continue
            subs = h.get("목", [])
            if isinstance(subs, dict):
                subs = [subs]
            for s in (subs or []):
                if str(s.get("목번호", "")).strip().rstrip(".") == str(sub_no):
                    return _norm(s.get("목내용"))
    return None


def resolve_from_local(
    law_name: str, art_no: str, para_no: str | None,
    item_no: str | None, sub_no: str | None, eff_date: str,
) -> dict | None:
    """
    로컬 JSON에서 조/항/호/목 텍스트 직접 추출.
    반환: {version_key, article_id, para_no, item_no, sub_no, text, level}
    """
    sk = _infer_slug_kind(law_name)
    if not sk:
        return None
    slug, kind = sk

    ver = find_version(slug, kind, eff_date)
    if not ver:
        return None
    version_key, mst_file = ver
    if not mst_file:
        return None

    raw = _load_mst(slug, kind, mst_file)
    if not raw:
        return None

    try:
        entries = raw["법령"]["조문"]["조문단위"]
        if isinstance(entries, dict):
            entries = [entries]
    except (KeyError, TypeError):
        return None

    art_entry = _find_article_entry(entries, art_no)
    if not art_entry:
        return None

    art_id = f"ART_{art_no}"
    art_text = _norm(art_entry.get("조문내용", ""))

    # 목 레벨 (항+호+목)
    if sub_no and item_no:
        text = _extract_subitem_text(art_entry, para_no or "", item_no, sub_no)
        if text:
            return {"version_key": version_key, "article_id": art_id,
                    "para_no": para_no, "item_no": item_no, "sub_no": sub_no,
                    "text": text, "level": "subitem"}

    # 호 레벨 (항+호 또는 항 없이 바로 호)
    if item_no:
        text = _extract_item_text(art_entry, para_no or "", item_no)
        if text:
            return {"version_key": version_key, "article_id": art_id,
                    "para_no": para_no, "item_no": item_no, "sub_no": None,
                    "text": text, "level": "item"}

    # 항 레벨
    if para_no:
        text = _extract_para_text(art_entry, para_no)
        if text:
            return {"version_key": version_key, "article_id": art_id,
                    "para_no": para_no, "item_no": None, "sub_no": None,
                    "text": text, "level": "paragraph"}

    # 조 레벨 fallback
    return {"version_key": version_key, "article_id": art_id,
            "para_no": None, "item_no": None, "sub_no": None,
            "text": art_text, "level": "article"}


# ── target 문자열 파싱 ────────────────────────────────────────────────────────

_TARGET_RE = re.compile(
    r'^(.+?)\s+'
    r'제(\d+)조(?:의(\d+))?'
    r'(?:\s*제(\d+)항)?'
    r'(?:\s*제(\d+)호(?:의(\d+))?)?'
    r'(?:\s*([가-힣]목))?',
    re.UNICODE,
)

# 내부 참조 prefix 패턴 (이 법/이 영/시행령/시행규칙/제X조 등)
_INTERNAL_PREFIXES = re.compile(
    r'^(이\s*법|이\s*영|이\s*규칙|같은\s*법|같은\s*령|같은\s*영|같은\s*규칙|'
    r'동법|동령|본법|본령|'
    r'(?:해당\s*)?(?:같은\s*)?시행(?:령|규칙)|'  # "시행령 제X조", "해당 시행규칙 제X조"
    r'제\s*\d+)',
    re.UNICODE,
)

# 내부참조 조/항/호/목 추출 (법령명 없이 조문 번호만)
_INTERNAL_ART_RE = re.compile(
    r'제(\d+)조(?:의(\d+))?'
    r'(?:\s*제(\d+)항)?'
    r'(?:\s*제(\d+)호(?:의(\d+))?)?'
    r'(?:\s*([가-힣]목))?',
    re.UNICODE,
)

# prefix → target kind 결정
_INTERNAL_KIND_MAP = {
    # 명시적 "이 법" 계열
    "이법": "law", "같은법": "law", "동법": "law", "본법": "law",
    "이영": "decree", "같은령": "decree", "같은영": "decree", "동령": "decree", "본령": "decree",
    "이규칙": "rule", "같은규칙": "rule",
    # "시행령 제X조" 계열 (형제 법령)
    "시행령": "decree", "해당시행령": "decree", "같은시행령": "decree",
    "시행규칙": "rule", "해당시행규칙": "rule", "같은시행규칙": "rule",
}


def _clean_law_name(name: str) -> str:
    """「」 따옴표 제거, 공백 정규화."""
    name = name.strip()
    name = re.sub(r'[「」『』\"\']', '', name).strip()
    return name


def _base_law_name(law_name: str) -> str:
    """'법인세법 시행령' → '법인세법'. 이미 기본 법명이면 그대로."""
    for suffix in ("시행규칙", "시행령"):
        if law_name.endswith(suffix):
            return law_name[:-len(suffix)].strip()
    return law_name


def parse_target(target: str) -> dict | None:
    target = target.strip()
    if _INTERNAL_PREFIXES.match(target):
        return None
    m = _TARGET_RE.match(target)
    if not m:
        return None
    law_name = _clean_law_name(m.group(1))
    art_base = m.group(2)
    art_sub  = m.group(3)
    para_no  = m.group(4)
    item_no  = m.group(5)
    item_sub = m.group(6)
    sub_char = m.group(7)

    art_no = art_base + (f"_{art_sub}" if art_sub else "")
    return {
        "law_name": law_name,
        "art_no":   art_no,
        "para_no":  para_no,
        "item_no":  item_no,
        "sub_no":   item_sub or (sub_char.replace("목", "") if sub_char else None),
    }


def resolve_internal(
    target: str,
    citing_law_name: str,
    citing_scope: str,
    eff_date: str,
) -> dict | None:
    """
    내부참조 해소.
    citing_law_name: citing LawVersion의 법령명 (e.g. "법인세법 시행령")
    citing_scope: "LAW" | "DECREE" | "RULE"
    """
    target = target.strip()
    base = _base_law_name(citing_law_name)

    # 1. prefix 매칭: "이 법", "시행령", "제X조" 등
    km = re.match(
        r'^(이\s*법|이\s*영|이\s*규칙|같은\s*법|같은\s*령|같은\s*영|같은\s*규칙|'
        r'동법|동령|본법|본령|'
        r'(?:해당\s*)?(?:같은\s*)?시행(?:령|규칙))',
        target, re.UNICODE,
    )

    if km:
        prefix_key = re.sub(r'\s+', '', km.group(0))  # 전체 매칭 정규화
        # "해당시행령" → "시행령" 등으로 정규화
        prefix_key = re.sub(r'^해당', '', prefix_key)
        prefix_key = re.sub(r'^같은', '', prefix_key)
        kind = _INTERNAL_KIND_MAP.get(prefix_key)
        if not kind:
            return None
        if kind == "law":
            target_name = base
        elif kind == "decree":
            target_name = base + " 시행령"
        else:
            target_name = base + " 시행규칙"
    else:
        # "제X조..." — citing 법령 그대로
        target_name = citing_law_name
        kind = citing_scope.lower()
        if kind not in ("law", "decree", "rule"):
            return None

    # 2. slug 확인 (없으면 base 시도)
    sk = _infer_slug_kind(target_name)
    if not sk:
        sk = _infer_slug_kind(base)
        if sk:
            sk = (sk[0], kind)
    if not sk:
        return None

    # 3. 조/항/호/목 파싱
    m = _INTERNAL_ART_RE.search(target)
    if not m:
        return None
    art_base = m.group(1)
    art_sub  = m.group(2)
    para_no  = m.group(3)
    item_no  = m.group(4)
    item_sub = m.group(5)
    sub_char = m.group(6)
    art_no = art_base + (f"_{art_sub}" if art_sub else "")
    sub_no = item_sub or (sub_char.replace("목", "") if sub_char else None)

    return resolve_from_local(
        law_name=target_name,
        art_no=art_no,
        para_no=para_no,
        item_no=item_no,
        sub_no=sub_no,
        eff_date=eff_date,
    )


# ── Neo4j 조회 / 업데이트 ─────────────────────────────────────────────────────

def get_unresolved_targets(tx) -> list[dict]:
    # LawVersion OPTIONAL — ITCL 등 LawVersion 없는 법령도 포함
    # eff_date/pdate fallback: version_key = "YYYYMMDD_공포번호" 형식이므로 앞 8자리 추출
    result = tx.run("""
        MATCH (lt:LawTarget)
        WHERE lt.resolved_version_key IS NULL
        OPTIONAL MATCH (v:LawVersion {
            scope:       lt.scope,
            law_id:      lt.law_id,
            version_key: lt.version_key
        })
        OPTIONAL MATCH (l:Law {scope: lt.scope, id: lt.law_id})
        WITH lt, v, l,
             coalesce(v.effective_date,    split(lt.version_key, '_')[0]) AS eff_date,
             coalesce(v.promulgation_date, split(lt.version_key, '_')[0]) AS pdate
        RETURN lt.name        AS target,
               lt.scope       AS scope,
               lt.law_id      AS law_id,
               lt.version_key AS version_key,
               eff_date,
               pdate,
               l.name              AS citing_law_name,
               id(lt) AS lt_id
    """)
    return [dict(r) for r in result]


def batch_update_resolved(tx, batch: list[dict]) -> None:
    tx.run("""
        UNWIND $batch AS row
        MATCH (lt:LawTarget) WHERE id(lt) = row.lt_id
        SET lt.resolved_version_key = row.vkey,
            lt.resolved_article_id  = row.art_id,
            lt.resolved_para_no     = row.para_no,
            lt.resolved_item_no     = row.item_no,
            lt.resolved_sub_no      = row.sub_no,
            lt.resolved_text        = row.text,
            lt.resolved_level       = row.level
    """, batch=batch)


def batch_mark_unresolvable(tx, batch: list[dict]) -> None:
    tx.run("""
        UNWIND $batch AS row
        MATCH (lt:LawTarget) WHERE id(lt) = row.lt_id
        SET lt.resolved_version_key = 'UNRESOLVABLE',
            lt.unresolvable_reason  = row.reason
    """, batch=batch)


# ── 메인 ──────────────────────────────────────────────────────────────────────

def run(dry_run: bool = True) -> None:
    stats = defaultdict(int)
    level_counts = defaultdict(int)

    print("=== CrossRef Resolution (로컬 JSON 기반) ===")
    print("  law_id 캐시 빌드 중...", end=" ", flush=True)
    _build_law_id_cache()
    print(f"{len(_LAW_ID_NAME_CACHE)}개 법령 로드", flush=True)
    with driver.session() as s:
        rows = s.execute_read(get_unresolved_targets)
    print(f"  미해소 LawTarget: {len(rows)}건")

    # 중복 제거 (같은 target + citing_version)
    seen: dict[tuple, dict] = {}
    for r in rows:
        key = (r["target"], r["scope"], r["law_id"], r["version_key"])
        if key not in seen:
            seen[key] = r
    print(f"  고유 조합: {len(seen)}건\n")

    sample_count = 0

    def _print_sample(target, resolved):
        nonlocal sample_count
        if sample_count >= 5:
            return
        sample_count += 1
        level = resolved["level"]
        print(f"  [sample] {target}")
        print(f"    → {resolved['version_key']} | {resolved['article_id']}"
              f" | 항={resolved.get('para_no')} 호={resolved.get('item_no')}"
              f" 목={resolved.get('sub_no')} [{level}]")
        print(f"    텍스트: {resolved.get('text','')[:80]}...")
        print()

    # 결과 수집 (배치 처리용)
    resolved_batch: list[dict] = []
    unresolvable_batch: list[dict] = []

    for (target, *_), row in seen.items():
        eff_date = row.get("eff_date") or row.get("pdate") or "99991231"

        # 1. 외부 법령 참조 시도
        parsed = parse_target(target)
        if parsed:
            resolved = resolve_from_local(
                law_name=parsed["law_name"],
                art_no=parsed["art_no"],
                para_no=parsed["para_no"],
                item_no=parsed["item_no"],
                sub_no=parsed["sub_no"],
                eff_date=eff_date,
            )
            if resolved:
                level = resolved["level"]
                level_counts[level] += 1
                stats["resolved"] += 1
                resolved_batch.append({
                    "lt_id":   row["lt_id"],
                    "vkey":    resolved["version_key"],
                    "art_id":  resolved["article_id"],
                    "para_no": resolved.get("para_no"),
                    "item_no": resolved.get("item_no"),
                    "sub_no":  resolved.get("sub_no"),
                    "text":    (resolved.get("text") or "")[:2000],
                    "level":   resolved.get("level"),
                })
                _print_sample(target, resolved)
            else:
                stats["unresolvable"] += 1
                unresolvable_batch.append({"lt_id": row["lt_id"], "reason": "not_found"})
            continue

        # 2. 내부참조 시도 ("이 법", "같은 법", "시행령", "제X조" 등)
        if _INTERNAL_PREFIXES.match(target):
            citing_law_name = row.get("citing_law_name") or ""
            if not citing_law_name:
                cached = _LAW_ID_NAME_CACHE.get(str(row.get("law_id", "")))
                if cached:
                    citing_law_name = cached
            citing_scope = row.get("scope") or "LAW"
            if citing_law_name:
                resolved = resolve_internal(
                    target=target,
                    citing_law_name=citing_law_name,
                    citing_scope=citing_scope,
                    eff_date=eff_date,
                )
                if resolved:
                    level = resolved["level"]
                    level_counts[level] += 1
                    stats["resolved_internal"] += 1
                    resolved_batch.append({
                        "lt_id":   row["lt_id"],
                        "vkey":    resolved["version_key"],
                        "art_id":  resolved["article_id"],
                        "para_no": resolved.get("para_no"),
                        "item_no": resolved.get("item_no"),
                        "sub_no":  resolved.get("sub_no"),
                        "text":    (resolved.get("text") or "")[:2000],
                        "level":   resolved.get("level"),
                    })
                    _print_sample(f"[내부] {target}", resolved)
                    continue

            # citing_law_name 없거나 resolve 실패
            stats["skip_internal"] += 1
            unresolvable_batch.append({"lt_id": row["lt_id"], "reason": "internal_ref"})
            continue

        # 3. 패턴 미매칭
        stats["unresolvable"] += 1
        unresolvable_batch.append({"lt_id": row["lt_id"], "reason": "no_pattern"})

    print("=== 결과 ===")
    print(f"  ✅ 외부 참조 해소  : {stats['resolved']}")
    print(f"  ✅ 내부 참조 해소  : {stats['resolved_internal']}")
    print(f"  ⏭️  내부 참조 미해소: {stats['skip_internal']}")
    print(f"  ❌ 미해소          : {stats['unresolvable']}")
    print()
    print("  [해소 레벨 분포]")
    for lvl in ["subitem", "item", "paragraph", "article"]:
        print(f"    {lvl:12s}: {level_counts[lvl]}")

    if dry_run:
        print("\n(--dry-run: Neo4j 반영 없음. --run으로 실제 적용)")
    else:
        # 배치 쓰기 (2번 왕복으로 전체 처리)
        CHUNK = 500
        print(f"\n  Neo4j 반영 중... resolved={len(resolved_batch)}, unresolvable={len(unresolvable_batch)}", flush=True)
        for i in range(0, len(resolved_batch), CHUNK):
            chunk = resolved_batch[i:i+CHUNK]
            with driver.session() as s:
                s.execute_write(batch_update_resolved, chunk)
            print(f"    resolved {min(i+CHUNK, len(resolved_batch))}/{len(resolved_batch)}", flush=True)
        for i in range(0, len(unresolvable_batch), CHUNK):
            chunk = unresolvable_batch[i:i+CHUNK]
            with driver.session() as s:
                s.execute_write(batch_mark_unresolvable, chunk)
            print(f"    unresolvable {min(i+CHUNK, len(unresolvable_batch))}/{len(unresolvable_batch)}", flush=True)
        print("✅ LawTarget 속성 업데이트 완료 (노드 추가 0개)")

    driver.close()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run",     action="store_true")
    args = ap.parse_args()
    run(dry_run=not args.run)
