from __future__ import annotations

from dataclasses import dataclass, asdict,is_dataclass
from typing import Literal, Optional, Iterable
from collections import defaultdict
import os
import json

# ============================================================
# 1. Domain models
# ============================================================

LawType = Literal["LAW", "DECREE", "RULE"]


@dataclass(frozen=True)
class LawVersionMeta:
    """
    법령 버전의 '시간축 메타데이터' (LLM 이전 단계)
    """
    law_name: str
    law_type: LawType
    promulgated_at: str      # YYYYMMDD
    effective_at: str        # YYYYMMDD (없으면 promulgated_at)
    promulgation_no: str


@dataclass(frozen=True)
class VersionWindow(LawVersionMeta):
    """
    유효 기간이 계산된 버전
    """
    valid_from: str
    valid_to: Optional[str]  # None이면 현재 유효


# ============================================================
# 2. Law type mapping
# ============================================================

def get_law_type_from_raw_drf(drf: dict) -> LawType:
    base = drf["법령"]["기본정보"]
    kind = base.get("법종구분", {}).get("content")

    if kind == "법률":
        return "LAW"
    elif kind == "대통령령":
        return "DECREE"
    elif kind == "기획재정부령":
        return "RULE"
    else:
        raise ValueError(f"Unknown 법종구분: {kind}")


# ============================================================
# 3. Version index cache (read / write)
# ============================================================

VERSION_INDEX_ROOT = os.path.join("cache", "version_index")


def version_index_path(
    law_name: str,
    law_type: LawType,
) -> str:
    """
    version index 디렉터리 경로
    """
    path = os.path.join(VERSION_INDEX_ROOT, law_name, law_type)
    os.makedirs(path, exist_ok=True)
    return path


def load_version_index(
    law_name: str,
    law_type: LawType,
) -> list[LawVersionMeta]:
    base = version_index_path(law_name, law_type)
    if not os.path.exists(base):
        return []

    metas: list[LawVersionMeta] = []

    for fname in sorted(os.listdir(base)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(base, fname), "r", encoding="utf-8") as f:
            metas.append(LawVersionMeta(**json.load(f)))

    return metas


def save_version_index(
    law_name: str,
    law_type: LawType,
    metas: Iterable[LawVersionMeta],
) -> None:
    """
    version index를 '버전 파일 단위'로 저장
    """
    base = version_index_path(law_name, law_type)

    for m in metas:
        fname = f"{m.promulgated_at}_{m.promulgation_no}.json"
        path = os.path.join(base, fname)

        if os.path.exists(path):
            continue  # 이미 있으면 skip (캐쉬 의미!)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                asdict(m),
                f,
                ensure_ascii=False,
                indent=2,
            )


# ============================================================
# 4. DRF → version meta extraction
# ============================================================

def extract_version_meta_from_drf(drf: dict) -> LawVersionMeta:
    law = drf.get("법령")
    if not law:
        raise TypeError("원본 DRF 형식이 아님: '법령' 키 없음")

    base = law.get("기본정보", {})

    promulgated_at = base.get("공포일자")
    promulgation_no = base.get("공포번호")
    effective_at = base.get("시행일자") or promulgated_at

    law_name = base.get("법령명_한글")

    if not law_name or not promulgated_at or not promulgation_no:
        raise ValueError(
            f"필수 메타 누락: law_name={law_name}, "
            f"공포일자={promulgated_at}, 공포번호={promulgation_no}"
        )

    return LawVersionMeta(
        law_name=law_name,
        law_type=get_law_type_from_raw_drf(drf),  # 🔴 converted용 함수 쓰면 안 됨
        promulgated_at=str(promulgated_at),
        effective_at=str(effective_at),
        promulgation_no=str(promulgation_no),
    )

# ============================================================
# 5. Version index builder
# ============================================================

def build_version_index(drfs: Iterable[dict]) -> None:
    grouped: dict[tuple[str, LawType], dict[tuple[str, str], LawVersionMeta]] = defaultdict(dict)

    for drf in drfs:
        meta = extract_version_meta_from_drf(drf)
        key = (meta.law_name, meta.law_type)
        uniq_key = (meta.promulgated_at, meta.promulgation_no)
        grouped[key][uniq_key] = meta

    for (law_name, law_type), metas in grouped.items():
        ordered = sorted(
            metas.values(),
            key=lambda m: m.effective_at,
        )
        save_version_index(law_name, law_type, ordered)


# ============================================================
# 6. valid_from / valid_to 계산
# ============================================================

def build_version_windows(
    versions: list[LawVersionMeta],
) -> list[VersionWindow]:
    """
    시행일 기준으로 정렬된 version meta → valid window 계산
    """
    versions = sorted(versions, key=lambda v: v.effective_at)
    windows: list[VersionWindow] = []

    for idx, v in enumerate(versions):
        valid_from = v.effective_at
        valid_to = versions[idx + 1].effective_at if idx + 1 < len(versions) else None

        windows.append(
            VersionWindow(
                **asdict(v),
                valid_from=valid_from,
                valid_to=valid_to,
            )
        )

    return windows

def build_and_save_version_windows(
    law_name: str,
    law_type: LawType,
) -> list[VersionWindow]:
    metas = load_version_index(law_name, law_type)
    if not metas:
        return []

    windows = build_version_windows(metas)

    out_dir = os.path.join("cache", "version_window", law_name)
    os.makedirs(out_dir, exist_ok=True)

    path = os.path.join(out_dir, f"{law_type}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            [asdict(w) for w in windows],
            f,
            ensure_ascii=False,
            indent=2,
        )

    return windows


from typing import Iterable, Optional, Literal
from dataclasses import dataclass
import os, json

LAWTYPE = Literal["LAW", "DECREE", "RULE"]
VERSION_WINDOW_ROOT = os.path.join("cache", "version_window")

def version_window_path(law_name: str, law_type: LAWTYPE) -> str:
    """
    cache/version_window/{law_name}/{law_type}.json
    """
    base = os.path.join(VERSION_WINDOW_ROOT, law_name)
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f"{law_type}.json")


@dataclass(frozen=True)
class VersionWindow:
    law_name: str
    law_type: LAWTYPE
    promulgated_at: str
    effective_at: str
    promulgation_no: str
    valid_from: str
    valid_to: Optional[str]


def load_version_windows(law_name: str, law_type: LAWTYPE) -> list[VersionWindow]:
    """
    build_and_save_version_windows가 저장한 윈도우 캐시를 로드한다.
    """
    path = version_window_path(law_name, law_type)

    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    return [VersionWindow(**item) for item in raw]


# ============================================================
# 7. 기준일 기준 유효 버전 선택
# ============================================================

def find_effective_version(
    windows: Iterable[VersionWindow],
    기준일: str,
) -> Optional[VersionWindow]:
    """
    기준일에 유효한 단 하나의 버전 선택
    """
    candidates = [
        w for w in windows
        if w.valid_from <= 기준일
        and (w.valid_to is None or 기준일 < w.valid_to)
    ]

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda w: (w.valid_from, w.promulgation_no),
    )




from itertools import product

def overlap_window(a_from, a_to, b_from, b_to):
    start = max(a_from, b_from)
    end = min(
        a_to or "99991231",
        b_to or "99991231",
    )

    # ❗ 하루짜리/역전 구간 제거
    if start < end:
        return start, None if end == "99991231" else end

    return None, None



def build_integrated_sets(laws, decrees, rules):
    sets = []

    for law, dec, rule in product(laws, decrees, rules):
        # 1️⃣ law + decree
        s1, e1 = overlap_window(
            law.valid_from, law.valid_to,
            dec.valid_from, dec.valid_to,
        )
        if not s1:
            continue

        # 2️⃣ (law+decree) + rule
        s2, e2 = overlap_window(
            s1, e1,
            rule.valid_from, rule.valid_to,
        )
        if not s2:
            continue

        sets.append({
            "valid_from": s2,
            "valid_to": None if e2 == "99991231" else e2,
            "law": law,
            "decree": dec,
            "rule": rule,
        })

    return sets


INTEGRATED_CACHE_ROOT = "cache/integrated_snapshot"

def integrated_snapshot_path(law_name: str) -> str:
    os.makedirs(INTEGRATED_CACHE_ROOT, exist_ok=True)
    return os.path.join(
        INTEGRATED_CACHE_ROOT,
        f"{law_name}.json"
    )

def load_integrated_snapshots(law_name: str) -> list[dict]:
    path = integrated_snapshot_path(law_name)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)



def _jsonable(x):
    if is_dataclass(x):
        return asdict(x)
    return x

def save_integrated_snapshots(law_name: str, snapshots: list[dict]) -> None:
    path = integrated_snapshot_path(law_name)

    serializable = []
    for s in snapshots:
        serializable.append(
            {
                "set_key": s["set_key"],
                "valid_from": s["valid_from"],
                "valid_to": s["valid_to"],
                "snapshot_date": s["snapshot_date"],
                "law": _jsonable(s["law"]),
                "decree": _jsonable(s["decree"]),
                "rule": _jsonable(s["rule"]),
            }
        )

    with open(path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)



def build_integrated_snapshots(laws, decrees, rules):
    """
    build_integrated_sets()가 산출한 dict들을 snapshot 포맷으로 정규화한다.
    - set_key 생성
    - snapshot_date = valid_from
    - (중요) valid_from == valid_to 는 제거되어야 함 (build_integrated_sets 단계에서 이미 했거나 여기서 한번 더)
    """

    snapshots = []

    for s in build_integrated_sets(laws, decrees, rules):
        law = s["law"]
        dec = s["decree"]
        rule = s["rule"]

        valid_from = s["valid_from"]
        valid_to = s["valid_to"]

        if valid_to is not None and valid_from >= valid_to:
            continue

        snapshots.append(
            {
                "set_key": (
                    f"LAW:{law.promulgated_at}_{law.promulgation_no}|"
                    f"DECREE:{dec.promulgated_at}_{dec.promulgation_no}|"
                    f"RULE:{rule.promulgated_at}_{rule.promulgation_no}"
                ),
                "valid_from": valid_from,
                "valid_to": valid_to,
                "snapshot_date": valid_from,
                "law": asdict(law),
                "decree": asdict(dec),
                "rule": asdict(rule),
            }
        )

    return snapshots


def build_and_cache_integrated_snapshots(
    law_name: str,
    laws,
    decrees,
    rules,
) -> list[dict]:
    # 1️⃣ 기존 캐시 로드
    cached = load_integrated_snapshots(law_name)
    cached_keys = {s["set_key"] for s in cached}

    # 2️⃣ 새로 계산
    fresh = build_integrated_snapshots(laws, decrees, rules)

    # 3️⃣ 중복 제거 (set_key 기준)
    new_items = [
        s for s in fresh
        if s["set_key"] not in cached_keys
    ]

    if not new_items:
        return cached

    # 4️⃣ 병합 + 저장
    merged = cached + new_items
    save_integrated_snapshots(law_name, merged)

    return merged
