# nhtsa_rules/parser.py

import json
import os

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(CURRENT_DIR, "channel_rules.json")


def load_rules():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


RULES = load_rules()


def parse_code(code_str):
    """
    NHTSA 16자리 코드를 해석 (숫자형 좌표 자동 처리 로직 추가)
    """
    if not code_str or len(code_str) < 16:
        return {"original": code_str, "valid": False, "error": "Length"}

    # 1. Key Extraction
    obj_key = code_str[0:2]
    loc_b_key = code_str[2:6]
    loc_s_key = code_str[6:10]
    sens_key = code_str[12:14]
    axis_key = code_str[14:15]

    # 2. Mapping
    obj = RULES["codes"]["object"].get(obj_key, "Unknown")
    loc_b = RULES["codes"]["location_broad"].get(loc_b_key, "Unknown")

    # [Logic Upgrade] Specific Location 처리
    # JSON에 있으면 가져오고, 없는데 '숫자'라면 좌표로 해석
    loc_s = RULES["codes"]["location_specific"].get(loc_s_key)
    if loc_s is None:
        if loc_s_key.isdigit():
            loc_s = f"Matrix/Coord {loc_s_key}"  # 예: 0402 -> Matrix 0402
        else:
            loc_s = "Unknown"

    sens = RULES["codes"]["sensor_type"].get(sens_key, "Unknown")
    axis = RULES["codes"]["axis"].get(axis_key, "Unknown")

    # 3. Validity Check
    # Unknown이 하나라도 있으면 Invalid로 볼 것인지, 아니면 유연하게 넘길지 결정
    # 여기서는 Broad Location과 Sensor Type은 필수라고 가정
    is_valid = (loc_b != "Unknown") and (sens != "Unknown")

    return {
        "original": code_str,
        "valid": is_valid,
        "object": obj,
        "location": f"{loc_b} - {loc_s}",
        "sensor_type": sens,
        "axis": axis,
        "debug_keys": [obj_key, loc_b_key, loc_s_key, sens_key],  # 디버깅용
    }
