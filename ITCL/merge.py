#ITCL/merge.py
from ITCL.run import extract_units_for_article


def _field(u, key):
    """객체든 dict든 안전하게 field 값을 꺼내는 통합 accessor"""
    if isinstance(u, dict):
        return u.get(key)
    return getattr(u, key, None)

#1) merge key 생성함수
def make_merge_key(article_id, level, ref):
    return f"{article_id}|{level}|{ref.get('para_no') or '-'}|{ref.get('item_no') or '-'}|{ref.get('subitem_no') or '-'}"


def index_norm_units(norm_units):
    indexed = {}
    for u in norm_units:
        article_id = _field(u, "article_id")
        level      = _field(u, "level")
        ref        = _field(u, "ref")

        key = make_merge_key(article_id, level, ref)
        indexed[key] = u
    return indexed


def index_cross_refs(cross_refs):
    indexed = {}
    for c in cross_refs:
        article_id = _field(c, "article_id")
        level      = _field(c, "level")
        ref        = _field(c, "ref")

        key = make_merge_key(article_id, level, ref)
        indexed[key] = c
    return indexed

def normalize_cross_refs(refs):
    out = []
    for r in refs or []:
        out.append({
            "type": _field(r, "type"),
            "target": _field(r, "target"),
            "note": _field(r, "note"),
        })
    return out

#3) Article 단위 merge 수행
def merge_units_for_article(art, norm_index, cref_index):
    merged_list = []

    units = extract_units_for_article(art)

    for u in units:
        article_id = art["id"]
        level = _field(u, "level")
        ref   = _field(u, "ref")

        key = make_merge_key(article_id, level, ref)

        base = {}

        # norm-unit
        if key in norm_index:
            n = norm_index[key]
            base = {
                "article_id": _field(n, "article_id"),
                "level": _field(n, "level"),
                "ref": _field(n, "ref"),
                "roles": _field(n, "roles") or [],
                "short_label": _field(n, "short_label"),
            }
        else:
            base = {
                "article_id": article_id,
                "level": level,
                "ref": ref,
                "roles": [],
                "short_label": None,
            }

        # cross-refs
        # 2) cross-ref 채우기
        if key in cref_index:
            c = cref_index[key]
            base["cross_refs"] = normalize_cross_refs(
                _field(c, "cross_refs")
            )
        else:
            base["cross_refs"] = []

        merged_list.append(base)

    return merged_list

#4) 최종 전체 merge 함수
def merge_into_converted(converted, norm_units, cross_refs):
    
    norm_index = index_norm_units(norm_units)
    cref_index = index_cross_refs(cross_refs)

    for ch in converted["chapters"]:
        
        for art in ch.get("articles", []):
            art["norm_units"] = merge_units_for_article(art, norm_index, cref_index)
        
        for sec in ch.get("sections", []):
            for art in sec.get("articles", []):
                art["norm_units"] = merge_units_for_article(art, norm_index, cref_index)

            for sub in sec.get("subdivisions", []):
                for art in sub.get("articles", []):
                    art["norm_units"] = merge_units_for_article(art, norm_index, cref_index)

    return converted


# article_summary 붙이기
def attach_article_summaries(merged_json, summary_list):
    # 요약 dict로 색인 (객체/딕트 둘 다 지원)
    summary_map = {}
    for s in summary_list:
        aid = _field(s, "article_id")
        if not aid:
            continue
        summary_map[aid] = s

    def patch_article(art):
        aid = art["id"]
        if aid in summary_map:
            s = summary_map[aid]
            art["article_summary"]    = _field(s, "article_summary")
            art["article_purpose"]    = _field(s, "article_purpose")
            art["article_key_topics"] = _field(s, "article_key_topics") or []
        else:
            # summary 없는 경우 placeholder라도
            art["article_summary"]    = None
            art["article_purpose"]    = None
            art["article_key_topics"] = []
        return art

    # 계층 전체 순회
    for ch in merged_json["chapters"]:
        for art in ch.get("articles", []):
            patch_article(art)

        for sec in ch.get("sections", []):
            for art in sec.get("articles", []):
                patch_article(art)

            for sub in sec.get("subdivisions", []):
                for art in sub.get("articles", []):
                    patch_article(art)

    return merged_json

