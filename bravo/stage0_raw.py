# stage0_raw.py

from load_file.read_raw import extract_clean_text
from load_file.splitter import refine_paragraphs
from pathlib import Path

def step_raw_and_paragraphs(pdf_path: str, case_id: str):
    from utils.cache import save_cache, load_cache
    cached = load_cache(case_id, "paragraphs.json")
    if cached:
        # cached가 list일 가능성 있으니 dict 형태로 래핑
        raw_cached = load_cache(case_id, "raw.json")
        return {
            "raw": raw_cached.get("raw"),
            "cleaned": raw_cached.get("cleaned"),
            "paragraphs": cached
        }

    raw, cleaned = extract_clean_text(pdf_path)
    paragraphs = refine_paragraphs(cleaned)

    save_cache(case_id, "raw.json", {"raw": raw, "cleaned": cleaned})
    save_cache(case_id, "paragraphs.json", paragraphs)

    # 여기! 반드시 dict로 리턴해야 한다
    return {
        "raw": raw,
        "cleaned": cleaned,
        "paragraphs": paragraphs
    }
