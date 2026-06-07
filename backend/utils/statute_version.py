# utils/statute_version.py
"""
법령 버전 매칭 유틸리티

판결문에서 추출한 공포번호(예: 대통령령 제19893호)를 기반으로
해당 버전의 법령 정보를 조회합니다.

조회 순서:
  1. ITCL(국제조세조정법 계열) → Neo4j IntegratedSnapshot set_key에서 매칭
  2. 그 외 세법 → 로컬 _version_index.json (법령정보센터 DRF 다운로드)
  3. 인덱스 없을 경우 → Claude 지식 기반 조회 (uncertainty 표시)
"""

import json
import os
import re
from pathlib import Path
from typing import Optional

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

_llm = ChatOpenAI(model="gpt-4.1", temperature=0)

# 로컬 법령 버전 DB 루트
_LAW_DB_ROOT = Path(__file__).parent.parent.parent / "law"

# ITCL 계열 법령명 (Neo4j에 보유 중인 법령)
_ITCL_LAW_NAMES = {
    "국제조세조정에 관한 법률",
    "국제조세조정법",
    "국조법",
    "국제조세조정에 관한 법률 시행령",
    "국조법 시행령",
    "국제조세조정에 관한 법률 시행규칙",
    "국조법 시행규칙",
}

# 로컬 DB 보유 법령 → (slug, 법종) 매핑
_LOCAL_DB_LAWS: dict[str, tuple[str, str]] = {
    "국세기본법":      ("gukse_basic",      "법"),
    "국세기본법 시행령": ("gukse_basic",    "령"),
    "국세기본법 시행규칙": ("gukse_basic",  "규칙"),
    "국세징수법":      ("gukse_collection", "법"),
    "국세징수법 시행령": ("gukse_collection","령"),
    "국세징수법 시행규칙": ("gukse_collection","규칙"),
    "법인세법":        ("corporate_tax",    "법"),
    "법인세법 시행령": ("corporate_tax",    "령"),
    "법인세법 시행규칙": ("corporate_tax",  "규칙"),
    "소득세법":        ("income_tax",       "법"),
    "소득세법 시행령": ("income_tax",       "령"),
    "소득세법 시행규칙": ("income_tax",     "규칙"),
    "부가가치세법":    ("vat",              "법"),
    "부가가치세법 시행령": ("vat",          "령"),
    "부가가치세법 시행규칙": ("vat",        "규칙"),
    "조세범처벌법":    ("tax_crime",        "법"),
    "조세범처벌절차법": ("tax_crime_proc",  "법"),
}


def _is_itcl_law(title: str) -> bool:
    return any(name in title for name in _ITCL_LAW_NAMES)


def _find_local_db_slug(title: str) -> tuple[str, str] | None:
    """법령명에서 로컬 DB slug와 법종 반환. 없으면 None."""
    for law_name, (slug, kind) in _LOCAL_DB_LAWS.items():
        if law_name in title:
            return slug, kind
    return None


def _load_local_index(slug: str, subdir: str) -> dict | None:
    """_version_index.json 로드. 없으면 None."""
    idx_file = _LAW_DB_ROOT / slug / subdir / "_version_index.json"
    if not idx_file.exists():
        return None
    try:
        return json.loads(idx_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def extract_article_text(slug: str, subdir: str, mst_filename: str, article_no: str) -> str | None:
    """
    저장된 MST JSON 파일에서 특정 조문 텍스트 추출.

    article_no: "26의2", "1", "2" 형태
    """
    law_file = _LAW_DB_ROOT / slug / subdir / mst_filename
    if not law_file.exists():
        return None
    try:
        data = json.loads(law_file.read_text(encoding="utf-8"))
    except Exception:
        return None

    first_key = next(iter(data), None)
    if not first_key:
        return None

    units = data[first_key].get("조문", {}).get("조문단위", [])
    if not isinstance(units, list):
        return None

    # 조문번호 정규화: "제26조의2" → "26의2", "26조의2" → "26의2", "26의2" → "26의2"
    normalized_no = re.sub(r"^제?(\d+)조?(의\d+)?$",
                           lambda m: m.group(1) + (m.group(2) or ""),
                           article_no.strip())

    # DRF JSON 특성: 제26조의2 도 조문번호="26"으로 저장됨.
    # 조문내용 시작 "제N조의M" 패턴으로 매칭.
    # 예: "제26조의2(국세 부과의 제척기간)"
    base_no = re.match(r"^(\d+)", normalized_no)
    suffix = ""
    if base_no:
        rest = normalized_no[len(base_no.group(1)):]
        base_no = base_no.group(1)
        suffix = rest  # "의2" 또는 ""

    # 내용 시작 패턴 - "제26조의2(" or "제26조("
    if suffix:
        content_prefix = f"제{base_no}조{suffix}("
    else:
        content_prefix = f"제{base_no}조("

    def _build_full_text(unit: dict) -> str:
        """조문단위에서 전체 텍스트 구성 (조문내용 + 항/호/목 포함)"""
        parts = []
        heading = str(unit.get("조문내용", "")).strip()
        if heading:
            parts.append(heading)

        항s = unit.get("항", [])
        if isinstance(항s, dict):
            항s = [항s]
        for 항 in (항s or []):
            if not isinstance(항, dict):
                continue
            항txt = str(항.get("항내용", "")).strip()
            if 항txt:
                parts.append(항txt)
            호s = 항.get("호", [])
            if isinstance(호s, dict):
                호s = [호s]
            for 호 in (호s or []):
                if not isinstance(호, dict):
                    continue
                호txt = str(호.get("호내용", "")).strip()
                if 호txt:
                    parts.append("  " + 호txt)
        return "\n".join(parts)

    for unit in units:
        if not isinstance(unit, dict):
            continue
        unit_no = str(unit.get("조문번호", "")).strip()
        heading = str(unit.get("조문내용", "")).strip()

        # 1순위: 조문내용 시작이 정확한 패턴과 일치
        if heading.startswith(content_prefix):
            return _build_full_text(unit)

        # 2순위: suffix 없으면 번호 직접 매칭 (단, 의X 없는 것만)
        if not suffix and unit_no == base_no:
            if not re.match(r"^제\d+조의\d+", heading):
                return _build_full_text(unit)

    return None


def lookup_local_law_version(title: str, promulgation_no: str) -> dict | None:
    """
    로컬 버전 인덱스에서 '제XXX호로 개정되기 전' 버전을 조회.
    인덱스가 없거나 해당 번호를 찾지 못하면 None 반환.
    """
    info = _find_local_db_slug(title)
    if not info:
        return None
    slug, kind = info

    # 법종에 따라 subdir 결정
    if "시행규칙" in title:
        subdir = "rule"
    elif "시행령" in title:
        subdir = "decree"
    else:
        subdir = "law"

    index = _load_local_index(slug, subdir)
    if not index:
        return None

    pno_stripped = promulgation_no.lstrip("0")

    # 해당 공포번호 버전 찾기
    target = index.get(pno_stripped)
    if not target:
        return None

    # 날짜 기준 이전 버전 찾기
    all_versions = sorted(index.values(), key=lambda x: x["pdate"])
    enacted_date = target["pdate"]
    prior_list = [v for v in all_versions if v["pdate"] < enacted_date]

    if not prior_list:
        return {
            "source": "local_db",
            "promulgation_no": promulgation_no,
            "note": f"제{promulgation_no}호가 최초 버전이어서 이전 버전이 없습니다.",
            "enacted_version": target,
        }

    prior = prior_list[-1]
    return {
        "source": "local_db",
        "law_slug": slug,
        "promulgation_no": promulgation_no,
        "description": f"제{promulgation_no}호 시행 이전 적용 버전",
        "prior_version": prior,
        "enacted_version": target,
        "note": (
            f"제{promulgation_no}호({enacted_date} 공포) 이전 적용된 버전: "
            f"제{prior['pno']}호 ({prior['pdate']} 공포)"
        ),
    }


def _parse_promulgation_type_prefix(ptype: Optional[str]) -> str:
    """Neo4j set_key의 컴포넌트 접두어 반환"""
    if not ptype:
        return ""
    mapping = {"법률": "LAW", "대통령령": "DECREE", "부령": "RULE"}
    return mapping.get(ptype, "")


def lookup_itcl_version(promulgation_no: str, promulgation_type: Optional[str]) -> Optional[dict]:
    """
    "제XXXXX호로 개정되기 전의 것" → 해당 공포번호가 시행되기 **이전** 스냅샷을 반환합니다.

    set_key 형식: LAW_20201222_17651__DECREE_20210217_31448__RULE_20210316_00840
    - 법률 제15221호로 개정되기 전 → LAW_*_15221 스냅샷을 찾고, 그 valid_from 이전 스냅샷 반환
    - 대통령령 제29525호로 개정되기 전 → DECREE_*_29525 스냅샷을 찾고, 그 이전 스냅샷 반환
    """
    from neo4j import GraphDatabase

    no_padded = promulgation_no.zfill(5)
    patterns = [f"_{promulgation_no}__", f"_{promulgation_no}", f"_{no_padded}__", f"_{no_padded}"]

    try:
        driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
        )
        with driver.session() as session:
            # 1단계: 해당 공포번호가 포함된 스냅샷의 valid_from 확인
            enacted_from = None
            enacted_key = None
            for pat in patterns:
                rows = session.run(
                    """
                    MATCH (s:IntegratedSnapshot)
                    WHERE s.set_key CONTAINS $pat
                    RETURN s.set_key AS set_key, s.valid_from AS valid_from
                    ORDER BY s.valid_from ASC
                    LIMIT 1
                    """,
                    {"pat": pat},
                )
                r = rows.single()
                if r:
                    enacted_from = r["valid_from"]
                    enacted_key = r["set_key"]
                    break

            if not enacted_from:
                driver.close()
                return None

            # 2단계: 해당 스냅샷 **이전** 스냅샷 조회 (valid_from < enacted_from)
            prev_rows = session.run(
                """
                MATCH (s:IntegratedSnapshot)
                WHERE s.valid_from < $enacted_from
                RETURN s.set_key   AS set_key,
                       s.valid_from AS valid_from,
                       s.valid_to   AS valid_to
                ORDER BY s.valid_from DESC
                LIMIT 1
                """,
                {"enacted_from": enacted_from},
            )
            prev_list = [dict(r) for r in prev_rows]

        driver.close()

        if not prev_list:
            return {
                "source": "neo4j_itcl",
                "promulgation_no": promulgation_no,
                "note": f"제{promulgation_no}호가 최초 버전이어서 이전 스냅샷이 없습니다.",
                "enacted_key": enacted_key,
                "enacted_from": enacted_from,
            }

        prev = prev_list[0]
        return {
            "source": "neo4j_itcl",
            "promulgation_no": promulgation_no,
            "promulgation_type": promulgation_type,
            "description": f"제{promulgation_no}호 시행 이전 적용 버전",
            "prior_snapshot": {
                "set_key": prev["set_key"],
                "valid_from": prev["valid_from"],
                "valid_to": prev["valid_to"],
            },
            "enacted_snapshot_key": enacted_key,
            "note": (
                f"제{promulgation_no}호({enacted_from} 시행) 이전에 적용된 버전: "
                f"{prev['valid_from']} ~ {prev['valid_to']}"
            ),
        }

    except Exception as e:
        return {"source": "neo4j_itcl", "error": str(e)}


def lookup_general_law_version(
    title: str,
    promulgation_no: str,
    promulgation_type: Optional[str],
    effective_before: Optional[str],
    article_ref: str = "",
) -> dict:
    """
    ITCL 외 법령(국세기본법, 법인세법 등)의 역사적 버전을
    Claude 지식 기반으로 조회합니다.

    반환 결과에는 항상 uncertainty 플래그가 포함됩니다.
    정확한 조문 전문이 필요하면 법제처 API로 검증하세요.
    """
    ptype_str = promulgation_type or "법령"
    before_str = f", {effective_before} 이전 시행본" if effective_before else ""

    prompt = (
        "당신은 한국 세법·조세법 전문가다. 아래 법령 버전 정보를 확인하고 알려진 내용을 답하라.\n\n"
        f"법령: {title}\n"
        f"공포: {ptype_str} 제{promulgation_no}호{before_str}\n"
        f"조문 참조: {article_ref or '(명시 없음)'}\n\n"
        "다음을 JSON으로 반환하라:\n"
        '{"law_name": "법령의 공식 명칭", '
        '"promulgation_date": "공포일 (알면 YYYY-MM-DD, 모르면 null)", '
        '"effective_date": "시행일 (알면 YYYY-MM-DD, 모르면 null)", '
        '"version_context": "이 공포번호 버전의 주요 개정 내용 또는 맥락 (2~3문장)", '
        '"article_content": "해당 조문의 내용 요약 (알면 기술, 확실하지 않으면 null)", '
        '"confidence": "high | medium | low", '
        '"verification_needed": true}'
    )

    resp = _llm.invoke([HumanMessage(content=prompt)])
    import json
    try:
        data = json.loads(resp.content.strip())
    except Exception:
        data = {
            "version_context": resp.content,
            "confidence": "low",
            "verification_needed": True,
        }

    data["source"] = "claude_knowledge"
    data["promulgation_no"] = promulgation_no
    data["promulgation_type"] = promulgation_type
    data["note"] = (
        "⚠️ Claude 지식 기반 조회 — 법제처 API 또는 국가법령정보센터에서 검증 권장"
    )
    return data


def resolve_citation_version(citation: "CitationItem") -> Optional[dict]:
    """
    CitationItem의 공포번호를 기반으로 법령 버전을 조회합니다.
    is_prior_version=True이고 promulgation_no가 있을 때만 실행됩니다.

    조회 순서:
      ITCL 계열 → Neo4j (데이터 있을 때만) → 없으면 Claude fallback
      그 외 법령 → Claude 지식
    """
    if not citation.is_prior_version or not citation.promulgation_no:
        return None

    title = citation.title
    pno = citation.promulgation_no
    ptype = citation.promulgation_type
    eff_before = citation.effective_before

    # 1. ITCL 계열 → Neo4j 먼저 시도
    if _is_itcl_law(title):
        result = lookup_itcl_version(pno, ptype)
        if result and "error" not in result and "prior_snapshot" in result:
            return result
        neo4j_note = (
            result.get("note", "") if result else
            f"Neo4j ITCL DB에 제{pno}호 버전 없음 (DB 범위: 2020년 이후)"
        )
        claude_result = lookup_general_law_version(
            title=title,
            promulgation_no=pno,
            promulgation_type=ptype,
            effective_before=eff_before,
            article_ref=title,
        )
        claude_result["neo4j_attempted"] = True
        claude_result["neo4j_note"] = neo4j_note
        return claude_result

    # 2. 로컬 DB 보유 법령 → 버전 인덱스 조회
    local_result = lookup_local_law_version(title, pno)
    if local_result:
        return local_result

    # 3. 그 외 → Claude 지식
    return lookup_general_law_version(
        title=title,
        promulgation_no=pno,
        promulgation_type=ptype,
        effective_before=eff_before,
        article_ref=title,
    )
