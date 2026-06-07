#bravo/utils.py

import json
def dump_outline_pretty(obj, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(pretty_json(obj))

def pretty_json(obj):
    """
    BaseModel, dict, list 모두 예쁘게 프린트.
    """
    if hasattr(obj, "model_dump"):
        data = obj.model_dump()
    else:
        data = obj
    return json.dumps(data, ensure_ascii=False, indent=2)

def save_pretty_json(obj, path):
    if hasattr(obj, "model_dump"):
        data = obj.model_dump()
    else:
        data = obj

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

#원문에서 별지 제외 하기 
def truncate_sentence_final(case_dict):
    """
    sentence_final.json 구조에서
    'CONCLUSION' role이 마지막으로 등장한 문장까지 남기고
    그 이후 문장/문단은 모두 제거한다.
    """
    last_para_idx = -1
    last_sent_idx = -1

    # 1) 마지막 CONCLUSION 찾기
    for p_idx, para in enumerate(case_dict["paragraphs"]):
        for s_idx, s in enumerate(para.get("sentences", [])):
            role = s.get("role", "")
            if role and role.upper() == "CONCLUSION":
                last_para_idx = p_idx
                last_sent_idx = s_idx

    # 결론이 없다면 전체 사용
    if last_para_idx == -1:
        return case_dict

    # 2) truncate 수행
    new_paragraphs = []

    for p_idx, para in enumerate(case_dict["paragraphs"]):
        if p_idx < last_para_idx:
            new_paragraphs.append(para)
        elif p_idx == last_para_idx:
            # 마지막 결론 문장까지만 포함
            new_para = para.copy()
            new_para["sentences"] = para["sentences"][: last_sent_idx + 1]
            new_paragraphs.append(new_para)
        else:
            # conclusion 이후 paragraph는 전부 버림
            break

    case_dict["paragraphs"] = new_paragraphs
    return case_dict

#별지제거한 원문 청크로 묶기
def paragraphs_to_chunks(case_dict, max_length=2000):
    chunks = []
    buffer = []
    buffer_len = 0

    for para in case_dict["paragraphs"]:
        texts = [s["sentence"] for s in para.get("sentences", []) if s.get("sentence")]
        para_text = " ".join(texts).strip()

        if not para_text:
            continue

        if buffer_len + len(para_text) > max_length and buffer:
            chunks.append("\n\n".join(buffer).strip())
            buffer = []
            buffer_len = 0

        buffer.append(para_text)
        buffer_len += len(para_text) + 1

    if buffer:
        chunks.append("\n\n".join(buffer).strip())

    return chunks

from collections import defaultdict
# 키워드 반복 제거, 빈도수 클러스터링
def build_signature_map(keyword_map):
    # 1) keyword frequency
    freq = defaultdict(int)
    for issue, kws in keyword_map.items():
        for kw in kws:
            freq[kw] += 1

    # 2) reverse map: keyword -> issues
    keyword_to_issues = defaultdict(list)
    for issue, kws in keyword_map.items():
        for kw in kws:
            keyword_to_issues[kw].append(issue)

    # 3) classification based on frequency
    signature = {
        "unique": [],   # 한 이슈에서만 등장
        "medium": [],   # 2~4개
        "common": []    # 거의 모든 이슈에 등장 (일반 anchor)
    }

    for kw, count in freq.items():
        if count == 1:
            signature["unique"].append(kw)
        elif count <= 4:
            signature["medium"].append(kw)
        else:
            signature["common"].append(kw)

    return {
        "keyword_freq": dict(freq),
        "keyword_to_issues": dict(keyword_to_issues),
        "signature": signature
    }
