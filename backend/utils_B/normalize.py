import re
from typing import List, Dict, Any, Literal
# ---------------------------------------------------------
# 조문 조회 (set_key 기준, LAW / DECREE / RULE)
# ---------------------------------------------------------
_ART_INPUT_RE = re.compile(r"[^0-9의]")

def normalize_article_input(raw: str) -> str:
    """
    "65" / "65조" / "65 의 2" / "65의2"  -> "65" or "65_2"
    """
    if raw is None:
        return ""

    s = raw.strip()
    s = s.replace("조", "")
    s = s.replace(" ", "")
    s = _ART_INPUT_RE.sub("", s)

    if not s:
        return ""

    if "의" in s:
        base, sub = s.split("의", 1)
        base = re.sub(r"[^0-9]", "", base)
        sub = re.sub(r"[^0-9]", "", sub)
        if not base or not sub:
            return ""
        return f"{int(base)}_{int(sub)}"

    base = re.sub(r"[^0-9]", "", s)
    if not base:
        return ""
    return f"{int(base)}"


def to_article_id(normalized: str) -> str:
    # "65" -> "ART_65", "65_2" -> "ART_65_2"
    return f"ART_{normalized}"
