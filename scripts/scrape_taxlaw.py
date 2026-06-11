"""
taxlaw.nts.go.kr 스크래퍼
- 판례(55,124), 사전답변(4,997), 질의회신(132,552), 과세기준자문(1,015), 법제처(991)
- 저장 위치: taxlaw/data/{category}/{category}.jsonl
- Resume 지원: 이미 저장된 doc_id 건너뜀
- 요청마다 새 Session 생성 (ConnectionResetError 회피)
"""
import sys, re, json, requests, time, os, argparse
from pathlib import Path
from datetime import datetime
sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://taxlaw.nts.go.kr"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
     "Accept-Language": "ko-KR,ko;q=0.9"}
H_XHR = {**H,
          "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
          "X-Requested-With": "XMLHttpRequest",
          "Accept": "application/json, */*; q=0.01"}

CATEGORIES = {
    "prec": {
        "name": "판례",
        "collection": "precedent,precedent_gr",
        "dcm_cl_cd": "001_09",
        "warmup": "/pd/USEPDI001M.do",
        "expected": 55124,
    },
    "advice": {
        "name": "사전답변",
        "collection": "question,question_gr",
        "dcm_cl_cd": "001_01",
        "warmup": "/qt/USEQTJ001M.do",
        "expected": 4997,
    },
    "reply": {
        "name": "질의회신",
        "collection": "question,question_gr",
        "dcm_cl_cd": "001_02",
        "warmup": "/qt/USEQTJ001M.do",
        "expected": 132552,
    },
    "consult": {
        "name": "과세기준자문",
        "collection": "question,question_gr",
        "dcm_cl_cd": "001_03",
        "warmup": "/qt/USEQTJ001M.do",
        "expected": 1015,
    },
    "moj": {
        "name": "법제처해석례",
        "collection": "question,question_gr",
        "dcm_cl_cd": "002_01",
        "warmup": "/qt/USEQTJ001M.do",
        "expected": 991,
    },
}

VIEW_COUNT = 50   # 페이지당 문서 수
SLEEP_OK = 1.2   # 성공 후 대기 (초)
SLEEP_ERR = 5.0  # 오류 후 대기 (초)
MAX_RETRY = 4    # 최대 재시도 횟수


def make_session(warmup: str) -> requests.Session:
    for attempt in range(3):
        try:
            s = requests.Session()
            s.headers.update(H)
            s.get(BASE + "/", timeout=12)
            time.sleep(0.3)
            s.get(BASE + warmup, timeout=12)
            time.sleep(0.3)
            return s
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(2)


def fetch_page(collection: str, dcm_cl_cd: str, start_count: int,
               warmup: str, view_count: int = VIEW_COUNT):
    """ASIPDI002PR01 호출, (body, top, error) 반환"""
    param = {
        "collectionName": collection,
        "sortField": "DCM_RGT_DTM/DESC",
        "startCount": start_count,
        "viewCount": view_count,
        "dcmClCdCtl": [dcm_cl_cd],
        "icldVcbCtl": [],
        "exclVcbCtl": [],
    }
    payload = {"actionId": "ASIPDI002PR01",
               "paramData": json.dumps(param, ensure_ascii=False)}
    for attempt in range(MAX_RETRY):
        try:
            sess = make_session(warmup)
            r = sess.post(BASE + "/action.do", data=payload,
                          headers={**H_XHR, "Referer": BASE + warmup},
                          timeout=25)
            if not r.text.strip() or r.text.strip()[0] not in ('{', '['):
                raise ValueError(f"non-JSON: {r.text[:80]!r}")
            j = r.json()
            data = j.get("data") if isinstance(j, dict) else None
            if data and "ASIPDI002PR01" in data:
                d = data["ASIPDI002PR01"]
                body = d.get("body", []) if isinstance(d, dict) else []
                top = d.get("top", []) if isinstance(d, dict) else []
                return body, top, None
            status = j.get("status", "?") if isinstance(j, dict) else "?"
            err_msg = j.get("message", "") if isinstance(j, dict) else ""
            return [], [], f"{status}: {err_msg}"
        except Exception as e:
            if attempt < MAX_RETRY - 1:
                time.sleep(SLEEP_ERR * (attempt + 1))
            else:
                return [], [], str(e)


def scrape_category(cat_key: str, out_dir: Path, max_docs: int = 0):
    cfg = CATEGORIES[cat_key]
    name = cfg["name"]
    collection = cfg["collection"]
    dcm_cl_cd = cfg["dcm_cl_cd"]
    warmup = cfg["warmup"]
    expected = cfg["expected"]

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{cat_key}.jsonl"

    # Resume: 이미 저장된 DOC_ID 로드
    seen_ids: set = set()
    if out_file.exists():
        with out_file.open(encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    doc_id = rec.get("DOC_ID") or rec.get("DOCID") or rec.get("NTST_FARE_INTC_GRP_SN")
                    if doc_id:
                        seen_ids.add(str(doc_id))
                except Exception:
                    pass
        print(f"[{name}] Resume: {len(seen_ids)}건 이미 저장됨")

    if max_docs and len(seen_ids) >= max_docs:
        print(f"[{name}] 이미 max_docs({max_docs}) 달성. 스킵.")
        return len(seen_ids)

    saved_count = len(seen_ids)
    # Resume: 이미 저장된 건수 기반 페이지 점프 (신규 문서가 앞 페이지에 추가될 수 있으므로 2페이지 여유)
    start_count = max(1, (len(seen_ids) // VIEW_COUNT) - 2)
    if start_count > 1:
        print(f"  [{name}] 페이지 {start_count}부터 재개 (이미 {len(seen_ids)}건 저장)")
    total_count = expected
    empty_pages = 0

    print(f"[{name}] 시작 (예상 {expected:,}건, viewCount={VIEW_COUNT}) → {out_file}")

    with out_file.open("a", encoding="utf-8") as f:
        while True:
            body, top, err = fetch_page(collection, dcm_cl_cd, start_count, warmup)

            if err:
                print(f"  [ERR p{start_count}] {err}")
                time.sleep(SLEEP_ERR)
                empty_pages += 1
                if empty_pages >= 5:
                    print(f"  [{name}] 연속 5회 오류. 중단.")
                    break
                start_count += 1
                continue

            if not body:
                empty_pages += 1
                if empty_pages >= 3:
                    print(f"  [p{start_count}] 연속 3회 빈 페이지. 완료.")
                    break
                start_count += 1
                time.sleep(SLEEP_OK)
                continue

            empty_pages = 0

            # top에서 totalCount 추출 (첫 페이지만)
            if start_count == 1 and top:
                try:
                    cat_map = top[0].get("categoryMap", {})
                    sub = cat_map.get("SUB_ID_CATEGORY", {})
                    if isinstance(sub, dict):
                        tc = sum(int(v) for v in sub.values() if str(v).isdigit())
                        if tc > 0:
                            total_count = tc
                            print(f"  [{name}] 실제 총 건수: {total_count:,}")
                except Exception:
                    pass

            new_in_page = 0
            for item in body:
                dcm = item.get("dcm", {})
                if not isinstance(dcm, dict):
                    continue
                doc_id = (dcm.get("DOC_ID") or dcm.get("DOCID") or
                          dcm.get("NTST_FARE_INTC_GRP_SN") or "")
                if str(doc_id) in seen_ids:
                    continue
                seen_ids.add(str(doc_id))

                # 저장할 레코드
                record = {
                    "category": cat_key,
                    "category_name": name,
                    "dcm_cl_cd": dcm_cl_cd,
                    "scraped_at": datetime.now().strftime("%Y%m%d_%H%M%S"),
                    **dcm,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                new_in_page += 1
                saved_count += 1

            pct = saved_count / total_count * 100 if total_count else 0
            print(f"  p{start_count:4d}: +{new_in_page} → 누적 {saved_count:,}/{total_count:,} ({pct:.1f}%)")

            if max_docs and saved_count >= max_docs:
                print(f"  [{name}] max_docs({max_docs}) 달성. 중단.")
                break

            if len(body) < VIEW_COUNT:
                print(f"  [{name}] 마지막 페이지 도달 ({len(body)} < {VIEW_COUNT}). 완료.")
                break

            start_count += 1
            time.sleep(SLEEP_OK)

    print(f"[{name}] 완료: {saved_count:,}건 저장 → {out_file}")
    return saved_count


def main():
    parser = argparse.ArgumentParser(description="taxlaw.nts.go.kr 스크래퍼")
    parser.add_argument("--categories", nargs="+",
                        choices=list(CATEGORIES.keys()) + ["all"],
                        default=["all"],
                        help="다운로드할 카테고리 (기본: all)")
    parser.add_argument("--out-dir", default="taxlaw/data",
                        help="저장 디렉토리 (기본: taxlaw/data)")
    parser.add_argument("--max-docs", type=int, default=0,
                        help="카테고리별 최대 문서 수 (0=무제한)")
    args = parser.parse_args()

    out_base = Path(args.out_dir)
    cats = list(CATEGORIES.keys()) if "all" in args.categories else args.categories

    print(f"=== taxlaw 스크래퍼 시작 ===")
    print(f"카테고리: {cats}")
    print(f"저장 위치: {out_base}")
    if args.max_docs:
        print(f"최대 문서 수: {args.max_docs:,}/카테고리")
    print()

    total_saved = 0
    for cat in cats:
        cat_dir = out_base / cat
        saved = scrape_category(cat, cat_dir, max_docs=args.max_docs)
        total_saved += saved
        print()

    print(f"=== 전체 완료: {total_saved:,}건 ===")


if __name__ == "__main__":
    main()
