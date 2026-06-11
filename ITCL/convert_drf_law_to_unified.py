#ITCL/convert_drf_law_to_unified.py

import copy, re
from ITCL.unified_law_schema import (LAW_SCHEMA,
    AMENDMENT_TEMPLATE,
    ARTICLE_TEMPLATE,CHAPTER_TEMPLATE,
    ITEM_TEMPLATE,PARAGRAPH_TEMPLATE,
    REV_REASON_TEMPLATE,SECTION_TEMPLATE,
    SUBDIVISION_TEMPLATE,SUBITEM_TEMPLATE,ANNEX_TEMPLATE
)


# ------------------------------------
# 0) chapter/section/subdivision/에서 숫자뽑기
# ------------------------------------

def extract_unit_no(text: str, unit_char: str):
    """
    제3절     → '3'
    제3절의2  → '3_2'
    제34조의3 → '34_3'
    제5관의10 → '5_10'
    """
    m = re.search(rf"제(\d+){unit_char}(의(\d+))?", text)
    if not m:
        return None

    base_no = m.group(1)            # e.g. '34'
    sub_no = m.group(3)             # e.g. '2' or None

    if sub_no:
        return f"{base_no}_{sub_no}"
    return base_no


# ------------------------------------
# 1) chapter/section/subdivision/article 판별 함수 (stub)
# ------------------------------------

def is_article_entry(entry, text):
    # 1) DRF가 조문이라고 명시한 경우
    if entry.get("조문여부") == "조문":
        return True
    
    # 2) "제숫자조" 패턴
    if re.match(r"^제\d+조", text):
        return True

    return False

def is_chapter(text):
    return bool(re.match(r"^제\d+장", text))


def is_section(text):
    return bool(re.match(r"^제\d+절", text))

def is_subdivision(text):
    return bool(re.match(r"^제\d+관", text))



def infer_source_type(meta: dict) -> str:
    """
    DRF 기본정보 + 법령명 suffix를 이용해
    source_type을 law / decree / rule 중 하나로 결정
    """

    # ---------------------------
    # 1️⃣ 법종구분 (최우선)
    # ---------------------------
    kind = meta.get("법종구분")

    if isinstance(kind, dict):
        kind = kind.get("content") or kind.get("code")

    if isinstance(kind, str):
        kind = kind.strip()

        if kind == "법률":
            return "LAW"

        # 시행령
        if kind in ("대통령령"):
            return "DECREE"

        # 시행규칙
        # (기획재정부령 / 총리령 / 부령 등 포함)
        if kind.endswith("부령") or kind== "총리령":
            # ⚠️ 여기서 대통령령은 이미 위에서 걸러짐
            return "RULE"

    # ---------------------------
    # 2️⃣ 법령명 suffix fallback
    # ---------------------------
    law_name = meta.get("법령명_한글", "")
    if isinstance(law_name, str):
        name = law_name.strip()

        # ⚠️ 순서 중요
        if name.endswith("시행규칙"):
            return "RULE"

        if name.endswith("시행령"):
            return "DECREE"

        if name.endswith("법"):
            return "LAW"

    # ---------------------------
    # 3️⃣ 최후 fallback
    # ---------------------------
    return "UNKNOWN"

# ------------------------------------
# 2) 변환기 메인
# ------------------------------------

#플래튼 함수
def flatten_lines(lines):
    flat = []
    for l in lines:
        if isinstance(l, list):
            flat.extend(flatten_lines(l))
        else:
            flat.append(l)
    return flat


#메인 함수 만들기
def convert_drf_law_to_unified(raw_json):

    root = raw_json["법령"]

    # 1. 스키마 복제 + 메타 채우기
    law = copy.deepcopy(LAW_SCHEMA)
    fill_metadata(law, root["기본정보"])

    # 2. 제개정 이유
    parse_revision_reasons(law, root.get("제개정이유"))

    # 3. 개정문
    parse_amendments(law, root.get("개정문"))

    # 4. 별표 (annexes)
    parse_annexes(law, root.get("별표"))

    # 5. 조문 스트림 (장/절/관/조문)
    entries = root["조문"]["조문단위"]
    parse_chapter_stream(law, entries)

    # 6. 부칙
    parse_addenda(law, root.get("부칙"))

    return law


def fill_metadata(law, meta):

    # 1) 기본 정보
    law["law_id"] = meta.get("법령ID")
    law["law_name"] = meta.get("법령명_한글")

    # 2) 날짜, 공포번호
    law["metadata"]["시행일자"] = meta.get("시행일자")
    law["metadata"]["공포일자"] = meta.get("공포일자")
    law["metadata"]["공포번호"] = meta.get("공포번호")

    # 3) 법종구분 (dict 또는 문자열)
    lg = meta.get("법종구분")
    if isinstance(lg, dict):
        law["metadata"]["법종구분"] = lg.get("content")
    else:
        law["metadata"]["법종구분"] = lg

    # 4) 소관부처 (dict 또는 문자열)
    dept = meta.get("소관부처")
    if isinstance(dept, dict):
        law["metadata"]["소관부처"] = dept.get("content")
    else:
        law["metadata"]["소관부처"] = dept

    # 5) source_type 
    law["source_type"] = infer_source_type(meta)


#개정문 파서 
def parse_amendments(law, amend_raw):
    if not amend_raw:
        return
    blocks = amend_raw.get("개정문내용")
    text = "\n".join(flatten_lines(blocks))
    node = copy.deepcopy(AMENDMENT_TEMPLATE)
    node["text"] = text
    law["amendments"].append(node)


#제개정이유 파서 
def parse_revision_reasons(law, rev_raw):
    if not rev_raw:
        return
    content = rev_raw.get("제개정이유내용", [])
    text = "\n".join(flatten_lines(content)) if content else ""
    node = copy.deepcopy(REV_REASON_TEMPLATE)
    node["text"] = text
    law["revision_reasons"].append(node)

#별표 파서 (parse_annexes)
def parse_annexes(law, annex_raw):
    if not annex_raw:
        return

    units = annex_raw.get("별표단위")
    if not units:
        return

    # 배열 아닌 경우 단일 dict → 배열로 래핑
    if isinstance(units, dict):
        units = [units]

    for u in units:
        node = copy.deepcopy(ANNEX_TEMPLATE)
        node["id"] = f"ANNEX_{u.get('별표번호')}"
        node["title"] = u.get("별표제목")
        node["number"] = u.get("별표번호")
        node["content_raw"] = "\n".join(flatten_lines(u.get("별표내용", [])))
        node["images"] = u.get("별표이미지파일명", [])
        node["pdf"] = u.get("별표PDF파일명")
        node["hwp"] = u.get("별표HWP파일명")

        law["annexes"].append(node)

def parse_chapter_stream(law, entries):
    current_chapter = None
    current_section = None
    current_subdivision = None

    for entry in entries:
        raw_text = entry.get("조문내용", "")

        # 텍스트 정규화
        if isinstance(raw_text, str):
            text = raw_text.strip()

        elif isinstance(raw_text, list):
            flat = flatten_lines(raw_text)
            text = " ".join(x.strip() for x in flat if isinstance(x, str))

        else:
            text = str(raw_text).strip()

        # ARTICLE
        if is_article_entry(entry, text):
            article = build_law_article_node(entry)   # ★ 시행령 전용 article builder

            if current_subdivision:
                current_subdivision["articles"].append(article)

            elif current_section:
                current_section.setdefault("articles", []).append(article)

            elif current_chapter:
                current_chapter.setdefault("articles", []).append(article)

            else:
                # 챕터 없이 바로 시작하는 법령(일부 시행규칙) → 기본 챕터 자동 생성
                default_ch = copy.deepcopy(CHAPTER_TEMPLATE)
                default_ch["id"] = "CH_GENERAL"
                default_ch["name"] = "일반"
                law["chapters"].append(default_ch)
                current_chapter = default_ch
                current_chapter.setdefault("articles", []).append(article)

            continue

        # CHAPTER
        if is_chapter(text):
            node = copy.deepcopy(CHAPTER_TEMPLATE)
            ch_no = extract_unit_no(text, "장") or entry["조문번호"]
            node["id"] = f"CH_{ch_no}"
            node["name"] = text

            law["chapters"].append(node)

            current_chapter = node
            current_section = None
            current_subdivision = None
            continue

        # SECTION
        if is_section(text):
            if current_chapter is None:
                raise ValueError("Section 등장 전에 Chapter가 없습니다.")

            node = copy.deepcopy(SECTION_TEMPLATE)
            sec_no = extract_unit_no(text, "절") or entry["조문번호"]
            node["id"] = f"{current_chapter['id']}_SEC_{sec_no}"
            node["name"] = text

            current_chapter["sections"].append(node)
            current_section = node
            current_subdivision = None
            continue

        # SUBDIVISION
        if is_subdivision(text):
            node = copy.deepcopy(SUBDIVISION_TEMPLATE)
            sub_no = extract_unit_no(text, "관") or entry["조문번호"]

            if current_section:
                node["id"] = f"{current_section['id']}_SUB_{sub_no}"
                current_section.setdefault("subdivisions", []).append(node)
            else:
                node["id"] = f"{current_chapter['id']}_SUB_{sub_no}"
                current_chapter.setdefault("subdivisions", []).append(node)

            node["name"] = text
            current_subdivision = node
            continue


def build_law_article_node(entry):
    article = copy.deepcopy(ARTICLE_TEMPLATE)

    raw = entry.get("조문내용", "")

    if isinstance(raw, list):
        flat = flatten_lines(raw)
        title_text = " ".join(x.strip() for x in flat)
    elif isinstance(raw, str):
        title_text = raw.strip()
    else:
        title_text = str(raw).strip()

    art_no = extract_unit_no(title_text, "조") or entry["조문번호"]
    article["id"] = f"ART_{art_no}"
    article["article_no"] = art_no
    article["title"] = title_text

    # raw_text는 prefix 제거 없이 flatten만
    raw_content = entry.get("조문내용", "")
    if isinstance(raw_content, str):
        flat_content = [raw_content]
    elif isinstance(raw_content, list):
        flat_content = flatten_lines(raw_content)
    else:
        flat_content = [str(raw_content)]

    article["raw_text"] = "\n".join(clean_text(line) for line in flat_content if line.strip())

    # 개정정보
    article["changed"] = (entry.get("조문변경여부") == "Y")
    article["effective_date"] = entry.get("조문시행일자")

    # 참고자료
    ref = entry.get("조문참고자료")
    if ref:
        article["reference_notes"] = ref if isinstance(ref, list) else [ref]

    # 항/호/목
    article["paragraphs"] = build_paragraphs(entry)

    return article

def build_paragraphs(entry):
    paras = []
    raw_paras = entry.get("항", [])

    # 항이 없으면 빈 리스트
    if not raw_paras:
        return []

    # string이면 무효
    if isinstance(raw_paras, str):
        return []

    # dict 하나만 들어온 경우
    if isinstance(raw_paras, dict):
        raw_paras = [raw_paras]

    for p in raw_paras:
        if not isinstance(p, dict):
            continue

        para = copy.deepcopy(PARAGRAPH_TEMPLATE)
        para["para_no"] = p.get("항번호")
        para["text"] = clean_text(p.get("항내용"))
        para["changed"] = (p.get("항제개정유형") in ["개정", "신설", "전부개정"])
        para["effective_date"] = p.get("항제개정일자문자열")

        para["items"] = build_items(p)
        paras.append(para)

    return paras


# -------------------------------------------
# ITEM (호)
# -------------------------------------------
def build_items(p):
    items = []
    raw_items = p.get("호", [])

    if isinstance(raw_items, dict):
        raw_items = [raw_items]

    for h in raw_items:
        if not isinstance(h, dict):
            continue

        item = copy.deepcopy(ITEM_TEMPLATE)
        item["item_no"] = h.get("호번호")
        item["text"] = clean_text(h.get("호내용"))

        item["subitems"] = build_subitems(h)
        items.append(item)

    return items


# -------------------------------------------
# SUBITEM (목)
# -------------------------------------------
def build_subitems(h):
    subs = []
    raw_sub = h.get("목", [])

    if isinstance(raw_sub, dict):
        raw_sub = [raw_sub]

    for m in raw_sub:
        if not isinstance(m, dict):
            continue

        sub = copy.deepcopy(SUBITEM_TEMPLATE)
        sub["subitem_no"] = m.get("목번호")
        sub["text"] = clean_text(m.get("목내용"))

        subs.append(sub)

    return subs


def parse_addenda(law, addenda_raw):
    if not addenda_raw:
        law["addenda"] = []
        return

    units = addenda_raw.get("부칙단위")
    parsed = []

    def normalize_text(x):
        if isinstance(x, list):
            return " ".join(normalize_text(i) for i in x)
        return str(x).strip()

    # 🔒 핵심: dict → list로 정규화
    if isinstance(units, dict):
        units = [units]

    if isinstance(units, list):
        for ad in units:
            if isinstance(ad, dict):
                parsed.append({
                    "date": ad.get("부칙공포일자"),
                    "content": normalize_text(ad.get("부칙내용"))
                })
            elif isinstance(ad, list):
                parsed.append({
                    "date": None,
                    "content": normalize_text(ad)
                })
            elif isinstance(ad, str):
                parsed.append({
                    "date": None,
                    "content": ad.strip()
                })

    elif isinstance(units, str):
        parsed.append({
            "date": None,
            "content": units.strip()
        })

    law["addenda"] = parsed




# prefix 제거용 정규식
PREFIX_RE = re.compile(r"^[①②③④⑤⑥⑦⑧⑨⑩\d]+\s*[.\)]?\s*")

def clean_text(v):
    """문자열/리스트를 모두 깔끔한 순수 텍스트로 변환"""
    if v is None:
        return ""
    
    # HTML 태그는 prefix 제거 대상이 아니다
    if isinstance(v, str) and "<" in v and ">" in v:
        return v.strip()

    # 리스트인 경우 flatten 후 합침
    if isinstance(v, list):
        flat = []
        for x in v:
            if isinstance(x, list):
                flat.extend(x)
            else:
                flat.append(x)
        v = " ".join([str(x).strip() for x in flat])

    if not isinstance(v, str):
        v = str(v)

    # prefix 제거 (① 1. 1) 등)
    return PREFIX_RE.sub("", v).strip()


