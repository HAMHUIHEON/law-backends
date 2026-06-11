"""
법원 판례 bravo 파이프라인 — 병렬 실행 버전

ThreadPoolExecutor로 N개 케이스를 동시에 처리.
각 케이스는 독립 cache 디렉토리를 사용하므로 파일 충돌 없음.
"""
from __future__ import annotations

import json
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv
load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

ROOT     = Path(__file__).parent.parent
API_DIR  = ROOT / "cases" / "court_api"
TMP_DIR  = ROOT / "cases" / "_tmp_txt"
TMP_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT))
from bravo.full_pipeline import run_full_pipeline
from utils.cache import save_cache, load_cache

_print_lock = Lock()

def log(msg: str):
    with _print_lock:
        print(msg, flush=True)


def make_case_id(api_path: Path) -> str:
    raw = json.loads(api_path.read_text(encoding="utf-8"))
    data = raw.get("PrecService", raw)
    court = re.sub(r'[\\/:*?"<>|\s,()（）]', '', data.get("법원명", "법원").strip())
    case_no = re.sub(r'[\\/:*?"<>|\s,()（）]', '', data.get("사건번호", api_path.stem).strip())
    if not court:
        court = "법원"
    if not case_no:
        case_no = api_path.stem
    return f"{court}_{case_no}"


# 시작 시 한 번만 빌드: case_no → 완료된 cache dir 이름 역인덱스
# 법원명 약칭 차이(서울고법 vs 서울고등법원)로 인한 중복 처리 방지용
_done_by_caseno: dict[str, str] = {}

def _build_done_index():
    global _done_by_caseno
    _done_by_caseno = {}
    for d in (ROOT / "cache").iterdir():
        if not d.is_dir():
            continue
        if (d / "issue_logic.json").exists():
            parts = d.name.split("_", 1)
            if len(parts) == 2:
                _done_by_caseno[parts[1]] = d.name  # case_no → dir_name


def is_done(case_id: str) -> bool:
    # 1차: 정확한 이름 매칭
    if (ROOT / "cache" / case_id / "issue_logic.json").exists():
        return True
    # 2차: case_no 기준 매칭 (법원명 약칭 차이 대응)
    case_no = case_id.split("_", 1)[1] if "_" in case_id else case_id
    return case_no in _done_by_caseno


def api_json_to_txt(api_path: Path, case_id: str) -> Path:
    raw_data = json.loads(api_path.read_text(encoding="utf-8"))
    data = raw_data.get("PrecService", raw_data)

    def clean(s: str) -> str:
        return s.replace("<br/>", "\n").replace("<br>", "\n").strip() if s else ""

    parts = []
    parts.append(f"사건명: {clean(data.get('사건명', ''))}")
    parts.append(f"법원: {clean(data.get('법원명', ''))}  사건번호: {clean(data.get('사건번호', ''))}  선고: {clean(data.get('선고일자', ''))}")
    parts.append("")

    if data.get("판시사항"):
        parts.append("판시사항\n" + clean(data["판시사항"]))
        parts.append("")
    if data.get("판결요지"):
        parts.append("판결요지\n" + clean(data["판결요지"]))
        parts.append("")
    if data.get("판례내용"):
        parts.append("판결이유\n" + clean(data["판례내용"]))
        parts.append("")
    if data.get("참조조문"):
        parts.append("참조조문\n" + clean(data["참조조문"]))
        parts.append("")
    if data.get("참조판례"):
        parts.append("참조판례\n" + clean(data["참조판례"]))
        parts.append("")

    txt_path = TMP_DIR / f"{case_id}.txt"
    txt_path.write_text("\n".join(parts), encoding="utf-8")
    return txt_path


def process_one(api_path: Path) -> tuple[str, bool, str]:
    case_id = make_case_id(api_path)
    if is_done(case_id):
        return case_id, False, "skip"
    try:
        txt_path = api_json_to_txt(api_path, case_id)
        result   = run_full_pipeline(str(txt_path))
        issue_logic_dict = (
            result["issue_logic"].model_dump()
            if hasattr(result.get("issue_logic"), "model_dump")
            else result.get("issue_logic")
        )
        result["issue_logic"] = issue_logic_dict
        save_cache(case_id, "final.json", result)
        return case_id, True, "ok"
    except Exception as e:
        return case_id, False, f"error: {e}\n{traceback.format_exc()}"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4, help="병렬 워커 수")
    parser.add_argument("--limit",   type=int, default=0,  help="최대 처리 건수 (0=전체)")
    args = parser.parse_args()

    api_files = sorted(API_DIR.glob("*.json"))
    # 완료 인덱스 빌드 (case_no 기반 중복 방지)
    _build_done_index()
    # case_id 미리 계산 (696건 JSON 읽기 1회)
    case_id_map = {f: make_case_id(f) for f in api_files}
    pending = [f for f in api_files if not is_done(case_id_map[f])]

    if args.limit:
        pending = pending[:args.limit]

    total   = len(api_files)
    skipped = total - len(pending)
    log(f"=== 병렬 bravo 파이프라인 (워커 {args.workers}개) ===")
    log(f"전체 {total}건 중 완료 {skipped}건 → 처리 대상 {len(pending)}건\n")

    done_cnt  = skipped
    error_cnt = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as exe:
        futures = {exe.submit(process_one, f): f for f in pending}
        for fut in as_completed(futures):
            case_id, ok, status = fut.result()
            if status == "skip":
                done_cnt += 1
            elif ok:
                done_cnt += 1
                elapsed  = time.time() - t0
                rate     = (done_cnt - skipped) / elapsed * 60  # 건/분
                remain   = len(pending) - (done_cnt - skipped)
                eta_min  = remain / rate if rate > 0 else 0
                log(f"  [완료] {case_id}  ({done_cnt}/{total})  속도 {rate:.1f}건/분  잔여 ~{eta_min:.0f}분")
            else:
                error_cnt += 1
                log(f"  [오류] {case_id}\n{status}")

    log(f"\n완료 — 성공 {done_cnt}건 / 오류 {error_cnt}건")


if __name__ == "__main__":
    main()
