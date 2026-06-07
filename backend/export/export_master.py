# export/export_master.py

from .export_a import build_export_A
from .export_b import build_export_B
from .export_c import build_export_C

#전체 export_case 하기
def export_case(case_id: str, type: str = "A"):
    if type == "A":
        return build_export_A(case_id)
    elif type == "B":
        return build_export_B(case_id)
    elif type == "C":
        return build_export_C(case_id)
    else:
        raise ValueError("Unknown export type")

#저장
def save_export(case_id, export_type, data):
    import os, json
    folder = os.path.join("export", case_id)
    os.makedirs(folder, exist_ok=True)
    fp = os.path.join(folder, f"export_{export_type}.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return fp


