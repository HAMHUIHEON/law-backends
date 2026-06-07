import os
import json
from pathlib import Path
from typing import Literal, Optional, Dict

LawType = Literal["LAW", "DECREE", "RULE"]


def _read_promulgation_meta_from_raw_drf_path(path: Path) -> tuple[str, str]:
    """
    원본 DRF JSON 파일에서 (공포일자, 공포번호)만 뽑는다.
    """
    with path.open("r", encoding="utf-8") as f:
        drf = json.load(f)

    base = drf.get("법령", {}).get("기본정보", {})
    promulgated_at = base.get("공포일자")
    promulgation_no = base.get("공포번호")

    if not promulgated_at or not promulgation_no:
        raise ValueError(f"공포 메타 누락: {path}")

    return str(promulgated_at), str(promulgation_no)


def build_drf_path_index(
    *,
    itcl_root: str,   # 예: "law/itcl"
    cache_path: str = "cache/drf_path_index_itcl.json",
) -> Dict[str, str]:
    """
    폴더 내 DRF들을 스캔해서:
      key = "LAW:20100101_09924"
      val = "/abs/or/rel/path/to/09924.json"
    형태로 인덱스를 만든다. (캐시 저장 포함)
    """
    root = Path(itcl_root)
    mapping = {
        "LAW": root / "law",
        "DECREE": root / "decree",
        "RULE": root / "rule",
    }

    index: Dict[str, str] = {}

    for law_type, folder in mapping.items():
        if not folder.exists():
            raise FileNotFoundError(f"DRF folder missing: {folder}")

        for path in sorted(folder.glob("*.json")):
            promulgated_at, promulgation_no = _read_promulgation_meta_from_raw_drf_path(path)
            key = f"{law_type}:{promulgated_at}_{promulgation_no}"

            # 중복 키가 생기면 위험하니 바로 터뜨리는 게 안전
            if key in index:
                raise RuntimeError(f"DRF index duplicate key: {key}\n- {index[key]}\n- {str(path)}")

            index[key] = str(path)

    # 캐시 저장
    Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    return index


def load_drf_path_index(cache_path: str = "cache/drf_path_index_itcl.json") -> Dict[str, str]:
    if not os.path.exists(cache_path):
        return {}
    with open(cache_path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_drf_paths_from_snapshot(
    *,
    snapshot: dict,
    index: Dict[str, str],
) -> tuple[str, str, str]:
    """
    snapshot(dict)에서 law/decree/rule의 (공포일자, 공포번호)를 읽고
    인덱스에서 DRF 경로 3개를 찾아 반환한다.
    """
    law = snapshot["law"]
    decree = snapshot["decree"]
    rule = snapshot["rule"]

    law_key = f'LAW:{law["promulgated_at"]}_{law["promulgation_no"]}'
    dec_key = f'DECREE:{decree["promulgated_at"]}_{decree["promulgation_no"]}'
    rule_key = f'RULE:{rule["promulgated_at"]}_{rule["promulgation_no"]}'

    try:
        law_path = index[law_key]
    except KeyError:
        raise FileNotFoundError(f"LAW DRF not found in index: {law_key}")

    try:
        dec_path = index[dec_key]
    except KeyError:
        raise FileNotFoundError(f"DECREE DRF not found in index: {dec_key}")

    try:
        rule_path = index[rule_key]
    except KeyError:
        raise FileNotFoundError(f"RULE DRF not found in index: {rule_key}")

    return law_path, dec_path, rule_path


def run_pipeline_for_integrated_snapshot(
    *,
    driver,
    snapshot: dict,
    itcl_root: str = "law/itcl",
    drf_index_cache_path: str = "cache/drf_path_index_itcl.json",
) -> None:
    """
    snapshot(set_key 기반으로 만든 dict)을 받아
    기존 run_full_analysis_pipeline(driver, law_drf_path, admrul_drf_path, rule_drf_path)를 호출한다.
    """
  
    # --------------------------------------------------
    # 0️⃣ idempotency 체크 (⭐ 추가)
    # --------------------------------------------------
    set_key = snapshot["set_key"]

    if is_integrated_snapshot_done(set_key):
        print(f"[SKIP] integrated snapshot already processed: {set_key}")
        return
    
    # --------------------------------------------------
    # 1️⃣ DRF path index 로드 (없으면 생성)
    # --------------------------------------------------
    index = load_drf_path_index(drf_index_cache_path)
    if not index:
        index = build_drf_path_index(itcl_root=itcl_root, cache_path=drf_index_cache_path)

    # --------------------------------------------------
    # 2️⃣ snapshot → DRF path 3개 resolve
    # --------------------------------------------------
    law_drf_path, admrul_drf_path, rule_drf_path = resolve_drf_paths_from_snapshot(
        snapshot=snapshot,
        index=index,
    )

    # --------------------------------------------------
    # 3️⃣ 기존 풀 파이프라인 호출 (그대로)
    # --------------------------------------------------
    from ITCL_integrated.pipeline import run_full_analysis_pipeline

    run_full_analysis_pipeline(
        driver=driver,
        law_drf_path=law_drf_path,
        admrul_drf_path=admrul_drf_path,
        rule_drf_path=rule_drf_path,
        snapshot = snapshot
    )

    # --------------------------------------------------
    # 4️⃣ 완료 마킹 (⭐ 추가)
    # --------------------------------------------------
    mark_integrated_snapshot_done(set_key)

    print(f"[DONE] integrated snapshot: {set_key}")


import os, json
INTEGRATED_DONE_ROOT = "cache/integrated_done"

def _done_path(set_key: str) -> str:
    os.makedirs(INTEGRATED_DONE_ROOT, exist_ok=True)
    safe = set_key.replace(":", "_").replace("|", "__")
    return os.path.join(INTEGRATED_DONE_ROOT, f"{safe}.json")

def is_integrated_snapshot_done(set_key: str) -> bool:
    return os.path.exists(_done_path(set_key))

def mark_integrated_snapshot_done(set_key: str) -> None:
    with open(_done_path(set_key), "w", encoding="utf-8") as f:
        json.dump({"set_key": set_key}, f, ensure_ascii=False, indent=2)
