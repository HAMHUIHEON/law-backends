# ITCL/domain_assign.py

DOMAIN_MAP = {

    # --- Ch 1 ---
    "제1장 총칙": "FOUNDATION",

    # --- Ch 2 ---
    "제2장 국제거래에 관한 조세의 조정": "TP",
    "제1절 국외특수관계인과의 거래에 대한 과세조정": "TP_CORE",
    "제1관 정상가격 등에 의한 과세조정": "TP_ALP",
    "제2관 정상가격 산출방법의 사전승인": "APA",
    "제3관 국제거래 자료 제출 및 가산세 적용 특례": "DOCUMENTATION",
    "제4관 국세의 정상가격과 관세의 과세가격의 조정": "TP_CUSTOMS",
    "제2절 국외지배주주 등에게 지급하는 이자에 대한 과세조정": "THIN_CAP",
    "제3절 특정외국법인의 유보소득에 대한 합산과세": "CFC",
    "제3절의2 국외투과단체에 귀속되는 소득에 관한 과세특례": "TRANSPARENT_ENTITY", #제34조의2
    "제4절 국외 증여에 대한 증여세 과세특례": "GIFT_TAX",

    # --- Ch 3 ---
    "제3장 국가 간 조세 행정 협조": "ADMIN_COOP",   
    "제1절 국가 간 조세협력": "EOI",
    "제2절 상호합의절차": "MAP",

    # --- Ch 4 ---
    "제4장 해외자산의 신고 및 자료 제출": "FOREIGN_ASSET_REPORTING",
    "제1절 해외금융계좌의 신고": "FOREIGN_BANK_ACCOUNT_REPORT",
    "제2절 해외현지법인 등의 자료 제출": "FOREIGN_SUBSIDIARY_REPORTING",

    # --- Ch 5 ---
    "제5장 글로벌최저한세의 과세": "GLOBE_PILLAR_TWO",
    "제1절 통칙": "GLOBE_SCOPE_AND_GENERAL_RULES",
    "제2절 추가세액의 계산": "GLOBE_TOP_UP_TAX_CALCULATION",
    "제3절 추가세액의 과세": "GLOBE_TOP_UP_TAX_IMPOSITION",
    "제4절 특례": "GLOBE_SAFE_HARBOURS_AND_EXCEPTIONS",
    "제5절 신고 및 납부 등": "GLOBE_COMPLIANCE_AND_ADMINISTRATION",

    # --- Ch 6 ---
    "제6장 벌칙": "PENALTIES"
}

def extract_law_key_from_set_key(set_key: str) -> str:
    """
    set_key: "LAW:20231231_19928|DECREE:...|RULE:..."
    return: "20231231_19928"
    """
    for part in set_key.split("|"):
        if part.startswith("LAW:"):
            return part.replace("LAW:", "").strip()
    raise ValueError(f"LAW part not found in set_key: {set_key}")

import json
from pathlib import Path
from typing import Dict, Any, Tuple

def load_domain_map_for_snapshot(
    *,
    snapshot: dict,
    law_drf_path: str,
    domain_map_dir: str = "debug/law_domain_maps",
) -> Dict[str, str]:
    """
    snapshot(set_key) → LAW_YYYYMMDD_NNNNN.json 로드
    + law_drf_path 검증까지 수행
    return: domains dict (name -> domain)
    """
    set_key = snapshot["set_key"]
    law_key = extract_law_key_from_set_key(set_key)           # "20221231_19191"
    domain_map_path = Path(domain_map_dir) / f"LAW_{law_key}.json"

    if not domain_map_path.exists():
        raise FileNotFoundError(f"Domain map file not found: {domain_map_path}")
    
    # print("[DOMAIN] set_key:", set_key)
    # print("[DOMAIN] law_key:", law_key)
    # print("[DOMAIN] domain_map_path:", domain_map_path)
    
    with open(domain_map_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # ✅ 안전장치: law_drf_path 검증
    expected = str(payload.get("law_drf_path", "")).replace("/", "\\")
    actual = str(law_drf_path).replace("/", "\\")
    if expected and expected != actual:
        raise ValueError(
            "Domain map law_drf_path mismatch.\n"
            f"- set_key: {set_key}\n"
            f"- domain_map: {domain_map_path}\n"
            f"- domain_map law_drf_path: {expected}\n"
            f"- resolved law_drf_path:   {actual}\n"
        )

    domains = payload.get("domains", {})
    # print("[DOMAIN] domains count:", len(domains))
    # 샘플 몇 개만
    # print("[DOMAIN] domains sample keys:", list(domains.keys())[:10])
    if not isinstance(domains, dict) or not domains:
        raise ValueError(f"'domains' missing/empty in {domain_map_path}")

    return domains

import re

def norm_title(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    # "<개정 ...>", "<신설 ...>" 같은 주석 제거 (필요 없으면 이 줄 빼도 됨)
    s = re.sub(r"\s*<[^>]*>\s*$", "", s).strip()
    return s

import re

CHAPTER_RE = re.compile(r"(제\s*\d+\s*장)")

def extract_chapter_key(title: str) -> str | None:
    if not title:
        return None
    m = CHAPTER_RE.search(title)
    if not m:
        return None
    return re.sub(r"\s+", "", m.group(1))  # "제1장"



def build_normalized_domain_lookup(domain_map: Dict[str, str]) -> Dict[str, str]:
    # 같은 norm key가 충돌하면 "먼저 나온 것" 유지 (충돌 자체가 이상이니 나중에 잡아도 됨)
    lookup: Dict[str, str] = {}
    for raw_title, domain in domain_map.items():
        key = extract_chapter_key(raw_title)
        if key and key not in lookup:
            lookup[key] = domain
    return lookup


def apply_domain_map(law: dict, domain_lookup: Dict[str, str]) -> None:
    for ch in law["chapters"]:
        key = extract_chapter_key(ch.get("name"))
        if key and key in domain_lookup:
            ch["domain"] = domain_lookup[key]

        # section / subdivision은 chapter 도메인 상속
        for sec in ch.get("sections", []):
            sec["domain"] = sec.get("domain") or ch.get("domain")

            for sub in sec.get("subdivisions", []):
                sub["domain"] = sub.get("domain") or sec.get("domain")


def assign_domains(law: dict) -> None:
    for ch in law["chapters"]:
        ch_domain = ch.get("domain")
        if not ch_domain:
            # print("[DOMAIN][ERROR] Missing chapter domain")
            # print("  chapter raw name:", ch.get("name"))
            # print("  chapter keys:", list(ch.keys()))
            raise ValueError(f"Chapter domain missing: {ch.get('name')}")

        # chapter 직속 articles
        for art in ch.get("articles", []):
            art["domain"] = art.get("domain") or ch_domain

        for sec in ch.get("sections", []):
            sec_domain = sec.get("domain") or ch_domain
            sec["domain"] = sec_domain

            for art in sec.get("articles", []):
                art["domain"] = art.get("domain") or sec_domain

            for sub in sec.get("subdivisions", []):
                sub_domain = sub.get("domain") or sec_domain
                sub["domain"] = sub_domain

                for art in sub.get("articles", []):
                    art["domain"] = art.get("domain") or sub_domain



def apply_domains_for_integrated_snapshot(
    *,
    snapshot: dict,
    law: dict,
    law_drf_path: str,
    domain_map_dir: str = "debug/law_domain_maps",
) -> None:
    """
    integrated snapshot 기준으로
    1) LAW domain map 로드
    2) normalized lookup 생성
    3) domain apply (선언된 곳만)
    4) domain assign (상속)
    
    ⚠️ law는 unified schema (chapters/sections/subdivisions/articles)를 가정
    ⚠️ 이 함수는 law를 inplace로 수정
    """

    # --------------------------------------------------
    # 1️⃣ 세트키 기반 LAW domain map 로드
    # --------------------------------------------------
    domain_map = load_domain_map_for_snapshot(
        snapshot=snapshot,
        law_drf_path=law_drf_path,
        domain_map_dir=domain_map_dir,
    )
    # domain_map: { "제1장 총칙": "FOUNDATION", ... }

    # --------------------------------------------------
    # 2️⃣ normalized lookup 생성
    #    (컨버터가 문자열을 안 건드리지만,
    #     domain map 쪽에 <신설 …> 같은 게 있으므로
    #     lookup 단계에서만 정규화)
    # --------------------------------------------------
    domain_lookup = build_normalized_domain_lookup(domain_map)

    # --------------------------------------------------
    # 3️⃣ 선언된 domain만 apply
    # --------------------------------------------------
    apply_domain_map(law, domain_lookup)

    # --------------------------------------------------
    # 4️⃣ 구조 기반 상속 (article까지 완결)
    # --------------------------------------------------
    assign_domains(law)
