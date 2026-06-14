# utils/citation_guard.py
"""
Citation Guard — LLM 생성 보고서의 판례 번호 환각 방어

LLM이 생성한 보고서에서 판례/재결 번호를 추출하고,
실제 검색된 데이터에 없는 번호는 [검증필요] 표시로 대체한다.
"""
import re
from typing import Sequence

# 판례 번호 패턴
_CASE_PATTERNS = [
    r'대법원\s*\d{4}[가-힣]+\d+',          # 대법원 2020두12345
    r'서울고(?:등)?법원\s*\d{4}[가-힣]+\d+',
    r'서울행정법원\s*\d{4}[가-힣]+\d+',
    r'\d{4}[가-힣]+\d+',                    # 2020두12345 (법원명 없는 경우)
    r'조심\s*\d{4}[가-힣서]+\d+',           # 조심 2022서1234
    r'국심\s*\d{4}[가-힣]+\d+',             # 국심 2019중1234
]
_CASE_RE = re.compile('|'.join(_CASE_PATTERNS))


def _extract_cited(text: str) -> list[str]:
    return list(dict.fromkeys(_CASE_RE.findall(text)))  # 순서 유지 dedup


def _build_valid_set(retrieved_sources: Sequence[list]) -> set[str]:
    """검색된 여러 소스에서 모든 케이스 번호 추출."""
    valid = set()
    for source in retrieved_sources:
        for r in (source or []):
            for field in ("case_no", "case_id", "dem_no", "doc_id"):
                v = r.get(field)
                if v:
                    valid.add(str(v).strip())
    return valid


def apply_citation_guard(
    report: str,
    *retrieved_sources: list,
    tag: str = "검증필요",
) -> tuple[str, list[str]]:
    """
    보고서에서 판례 번호를 추출하고, 검색 결과에 없는 번호를 표시한다.

    Args:
        report: LLM이 생성한 보고서 텍스트
        *retrieved_sources: 검색에 사용된 판례 목록들
        tag: 미검증 판례에 붙일 태그 (기본값 "검증필요")

    Returns:
        (수정된 보고서, 미검증 판례 번호 목록)
    """
    cited = _extract_cited(report)
    if not cited:
        return report, []

    valid = _build_valid_set(retrieved_sources)

    unverified = []
    result = report
    for c in cited:
        # 숫자만으로 된 케이스(너무 짧음)는 건너뜀
        if re.match(r'^\d{4}[가-힣]+\d+$', c) and len(c) < 8:
            continue
        # 검증 실패 시 표시
        normalized = re.sub(r'\s+', '', c)
        if not any(re.sub(r'\s+', '', v) == normalized for v in valid):
            result = result.replace(c, f"**[{tag}: {c}]**")
            unverified.append(c)

    return result, unverified
