# #ITCL/parser_itcl.py
# #(PDF → articles 구조화)

# """
# run_itcl_parser
#  ├─ read_raw_file                   # PDF → raw text
#  ├─ extract_clean_text              # 헤더/푸터 제거
#  └─ split_articles                  # 조문 split
#         └─ split_paragraphs        # 항(①) split
#                └─ extract_items     # 호(1.2.3) split

# """
# import re
# from pathlib import Path
# from langchain_community.document_loaders import PyMuPDFLoader

# PATH = r"국제조세조정에 관한 법률(법률)(제21065호)(20251001).pdf"

# # ============================================================
# # 0) 파일 로딩 (PyMuPDF 기준)
# # ============================================================
# def read_raw_file(path: str) -> str:
#     lower = path.lower()

#     if lower.endswith(".pdf"):
#         pages = PyMuPDFLoader(path).load()
#         return "\n".join(p.page_content for p in pages)

#     else:
#         return Path(path).read_text(encoding="utf-8", errors="ignore")


# # ============================================================
# # 1) 텍스트 정제 (헤더/푸터 제거만 담당)
# # ============================================================
# def extract_clean_text(raw_text: str) -> str:
#     lines = raw_text.splitlines()
#     clean_lines = []

#     for ln in lines:
#         ln_strip = ln.strip()

#         # 헤더/푸터 제거
#         if "법제처" in ln_strip or "국가법령정보센터" in ln_strip:
#             continue
#         # 페이지 번호 제거 (너무 단순한 숫자 한 줄)
#         if re.fullmatch(r"\d+", ln_strip):
#             continue

#         clean_lines.append(ln_strip)

#     full_text = "\n".join(clean_lines)

#     # 조문 앞에 강제 개행 넣기
#     # 예: "제8조(정상가격...)" 이런 패턴을 확실하게 분리
#     full_text = re.sub(r"(제\d+조\()", r"\n\1", full_text)

#     return full_text


# # ============================================================
# # 2) 전체 텍스트 → 조문 블록 파싱
# # ============================================================
# def split_articles(full_text: str):
#     raw_articles = re.split(r"(?=제\d+조\()", full_text)
#     articles = []
#     for block in raw_articles:
#         block = block.strip()
#         if not block.startswith("제"):
#             continue

#         m = re.match(r"제(\d+)조\(([^)]*)\)\s*(.*)", block, re.S)
#         if not m:
#             continue

#         num = int(m.group(1))
#         title = m.group(2).strip()
#         body = m.group(3).strip()

#         paragraphs = split_paragraphs(body)

#         articles.append(
#             {
#                 "article_no": num,
#                 "title": title,
#                 "paragraphs": paragraphs,
#                 "raw_body": body,
#             }
#         )

#     return articles


# # ============================================================
# # 3) 항(① ② …) 및 호(1. 2. …) 구조화
# # ============================================================
# CIRCLED_MAP = {
#     "①": "1",
#     "②": "2",
#     "③": "3",
#     "④": "4",
#     "⑤": "5",
#     "⑥": "6",
#     "⑦": "7",
#     "⑧": "8",
#     "⑨": "9",
#     "⑩": "10",
# }

# def split_paragraphs(body: str):

#     """
#     제n조(...) 단위로 조문을 분리하고, 각 조문 내부에서 항/호까지 구조화
#     """

#     for c, n in CIRCLED_MAP.items():
#         body = body.replace(c, f"\n@PARA_{n} ")

#     parts = [p.strip() for p in body.split("\n") if p.strip()]
#     paras = []
#     current = None

#     for p in parts:
#         if p.startswith("@PARA_"):
#             #새 항 시작
#             no, text = p.split(" ", 1)
#             idx = int(no.replace("@PARA_", ""))

#             current = {"para_no": idx, "text": text.strip(), "items": []}
#             paras.append(current)
#         else:
#             # 첫 항이 없을 수도 있음
#             if current is None:
#                 current = {"para_no": 0, "text": "", "items": []}
#                 paras.append(current)
#             current["text"] += " " + p.strip()

#     # 이제 para.text에 item(호)을 직접 뽑는다
#     for para in paras:
#         text = re.sub(r"\s+", " ", para["text"]).strip()
#         para["items"] = extract_items_from_para(text)
#         para["text"] = text  # 정리된 본문으로 저장

#     return paras

# def extract_items_from_para(text: str):
#     """
#     조문 항에서 item(1., 2., 3., ...)을 추출.
#     단, 개정일/신설일(<> 안쪽)은 item 대상으로 보지 않는다.
#     """

#     # 0) 원문은 그대로 두고, item 탐지를 위한 별도 work 텍스트 생성
#     work = re.sub(r"<[^>]*>", " ", text)   # <개정 ...>, <신설 ...> 같은 것 제거

#     # 1) 강력한 정규화 (work 기준)
#     work = re.sub(r"(\d+)\s*[\.\u002E]\s*", r"\1. ", work)

#     # 2) "1. ", "2. " 패턴만 찾기
#     matches = list(re.finditer(r"(\d+)\.\s", work))
#     if not matches:
#         return []

#     items = []
#     for i, m in enumerate(matches):
#         start = m.start()
#         item_no = int(m.group(1))

#         # 연도 같은 비정상 큰 숫자는 item으로 보지 않기 (안전장치)
#         if item_no >= 100:   # 1~99만 호 번호로 인정
#             continue

#         end = matches[i + 1].start() if i + 1 < len(matches) else len(work)
#         content = work[start:end]
#         content = re.sub(r"^\d+\.\s*", "", content).strip()

#         # 내용이 비어있으면 버림
#         if not content:
#             continue

#         items.append({"item_no": item_no, "text": content})

#     return items


# # ============================================================
# # 4) 최종 파이프라인 entry 함수
# # ============================================================
# def run_itcl_parser(path: str = PATH):
#     """
#     전체 파서 파이프라인을 한 번에 실행하는 엔트리 함수.
#     델타 엔진처럼 단일 run() 구조 확보.
#     """
#     raw = read_raw_file(path)
#     clean = extract_clean_text(raw)
#     articles = split_articles(clean)
#     return articles



# # 수동 테스트할 때만 실행
# if __name__ == "__main__":
#     arts = run_itcl_parser(PATH)

#     # 딱 8조만 확인
#     example = next(a for a in arts if a["article_no"] == 8)
#     from pprint import pprint
#     pprint(example)


# import os
# from ITCL.parser_itcl import (
#     read_raw_file,
#     extract_clean_text,
#     split_articles,
#     split_paragraphs,
# )
# from ITCL.ingest_itcl import (run_query,create_structure,create_article_with_norms,)


# def run_itcl_graph_build(pdf_path: str):
#     """
#     국제조세조정법 전체 그래프 생성 (원터치 파이프라인)
#     1) Neo4j 초기화
#     2) 상위 구조(Law/Chapter/Section/Subdivision) 생성
#     3) PDF → 조문 파싱
#     4) 조문을 Article/NormUnit으로 Neo4j에 삽입
#     """

#     print("⚠ Neo4j 초기화 중...")
#     run_query("MATCH (n) DETACH DELETE n")

#     print("⚠ Law 생성...")
#     run_query('CREATE (l:Law {id:"ITCL", name:"국제조세조정에 관한 법률"})')

#     print("⚠ 상위 구조(Graph Schema) 생성...")
#     create_structure(STRUCTURE)

#     # -------------------------
#     # PDF 로딩 및 파싱
#     # -------------------------
#     print("⚠ PDF 읽는 중...")
#     raw = read_raw_file(pdf_path)
#     clean = extract_clean_text(raw)
#     articles = split_articles(clean)

#     # 각 조문에 paragraphs 붙이기
#     for art in articles:
#         art["paragraphs"] = split_paragraphs(art["raw_body"])

#     # -------------------------
#     # Article & NormUnit 생성 --->llm생성 후 다시 수정해야함
#     # -------------------------
#     print("⚠ Article + NormUnit 생성 중...")

#     for ch in ARTICLE_SCHEMA["law"]["chapters"]:
#         for sec in ch.get("sections", []):
#             for sub in sec.get("subdivisions", []):
#                 for art_meta in sub.get("articles", []):
#                     # 파서에서 찾은 해당 조문 가져오기
#                     art_no = int(art_meta["id"].replace("ITCL_", ""))
#                     parsed_article = next(
#                         a for a in articles if a["article_no"] == art_no
#                     )

#                     # Neo4j에 Article + NormUnit 생성
#                     create_article_with_norms(art_meta, sub["id"])

#     print("🎉 ITCL 전체 그래프 빌드 완료!")