"""
Pulse Analysis & Data Loading Module.
FINAL CORRECTED VERSION: Allows 'DOOR' channels if they are 'SILL'.

[Correction based on Evidence]
- Validated via sensor_survey_report.csv:
  Channel '10DOORLERE...' corresponds to Description 'LEFT REAR SILL AX'.
- Action: Removed 'DOOR' from blacklist. Added logic to treat 'DOOR' names as Sills.
"""

import numpy as np
from nptdms import TdmsFile
from typing import Optional, Tuple, Dict, Any
from loguru import logger


class CrashPulseAnalyzer:
    def __init__(self, tdms_path: str):
        self.tdms_path = tdms_path
        self.tdms_file = None
        try:
            self.tdms_file = TdmsFile.read(tdms_path)
        except Exception as e:
            logger.error(f"Failed to read TDMS file: {tdms_path} -> {e}")

    def find_channel_by_name(self, channel_name: str) -> Optional[Any]:
        """Finds a TDMS channel by its exact name."""
        if not self.tdms_file:
            return None
        for group in self.tdms_file.groups():
            if channel_name in group:
                return group[channel_name]
        logger.warning(f"Channel '{channel_name}' not found in any group.")
        return None

    def find_vehicle_accel_channel(self) -> Optional[Any]:
        """
        NHTSA 관행 반영: 이름이 'DOOR'여도 설명이 'SILL'이면 차체 프레임 센서로 인정.
        우선순위: Rear Seat Crossmember > Rear Sill > B-Pillar > Side Sill
        """
        if not self.tdms_file:
            return None

        candidates = []

        for group in self.tdms_file.groups():
            for channel in group.channels():
                props = channel.properties
                name = channel.name.upper().strip()

                # 메타데이터 추출
                def get_val(keys):
                    for k in keys:
                        for pk in props.keys():
                            if k.upper() in pk.upper():
                                return str(props[pk]).upper()
                    return ""

                ins_com = get_val(["INST_INSCOM", "COMMENT", "DESCRIPTION"])
                ins_axis = get_val(["INST_AXIS", "AXIS", "D1AXIS"])
                sen_type = get_val(["INST_SENTYP", "SENTYP", "TYPE"])

                full_desc = f"{ins_com} {name}"

                # --- 1. 블랙리스트 (Blacklist) ---
                # [수정됨] 'DOOR' 삭제함 (DOOR 이름이 SILL인 경우가 많음)
                blacklist = [
                    "ENGINE",
                    "ENGN",  # 엔진
                    "MDB",
                    "BARRIER",
                    "SLED",  # 대차
                    "DUMMY",
                    "HEAD",
                    "CHEST",
                    "CHST",
                    "NECK",
                    "FEMUR",
                    "TIBIA",
                    "PELVIS",
                    "PELV",
                    "FOOT",
                    "SPINE",
                    "SPIN",  # 더미
                    "SEAT TRACK",
                    "SEAT CUSHION",  # 시트 레일/쿠션 (프레임 아님)
                    "STEER",
                    "WHEEL",
                    "WHEL",
                    "BRAKE",
                    "TIRE",
                    "SUSP",  # 섀시
                    "DASH",
                    "INSTRUMENT",  # 대시보드
                    "BUMP",
                    "BUMPER",  # 범퍼
                    "BAT",
                    "BATT",  # 배터리
                ]

                if any(bad in full_desc for bad in blacklist):
                    continue

                # 상대차량(20) 제외
                if name.startswith("20") or name.startswith("MDB"):
                    continue

                # --- 2. 가속도계 + X축 확인 ---
                is_accel = ("AC" in sen_type) or ("ACCEL" in sen_type) or ("AC" in name)

                is_x_axis = False
                if "XG" in ins_axis or "LONG" in ins_axis or ins_axis == "X":
                    is_x_axis = True
                elif "AC1" in name or "ACX" in name or "1P" in name or "_X" in name:
                    is_x_axis = True
                elif name.startswith("11") and "AC" in name:
                    is_x_axis = True

                if not (is_accel and is_x_axis):
                    continue

                # --- 3. [Target Selection] 화이트리스트 로직 ---
                score = 0
                loc_name = "Unknown"

                # 키워드 확인
                # NHTSA 데이터에서 'DOOR' 이름은 'SILL' 위치를 의미하는 경우가 대다수
                is_sill = any(k in full_desc for k in ["SILL", "ROCKER", "DOOR"])
                is_xmem = any(k in full_desc for k in ["CROSSMEMBER", "XMEM"])
                is_pillar = any(k in full_desc for k in ["PILLAR", "POST", "BPLL"])

                # 위치 확인 (Rear 우선)
                is_rear = ("REAR" in full_desc) or ("LERE" in name) or ("RIRE" in name)

                # [Rank 1] Rear Seat Crossmember (가장 견고)
                if is_xmem and is_rear:
                    score = 100
                    loc_name = f"Rear Seat Crossmember ({name})"

                # [Rank 2] Rear Sill (DOOR 이름 포함)
                elif is_sill and is_rear:
                    score = 95
                    loc_name = f"Rear Sill ({name})"

                # [Rank 3] Side Sill (Front/General)
                elif is_sill:
                    score = 80
                    loc_name = f"Side Sill ({name})"

                # [Rank 4] B-Pillar
                elif is_pillar and (
                    "B-" in full_desc or "BPLL" in name or "MID" in full_desc
                ):
                    score = 70
                    loc_name = f"B-Pillar ({name})"

                if score > 0:
                    candidates.append(
                        {"channel": channel, "score": score, "loc": loc_name}
                    )

        if candidates:
            candidates.sort(key=lambda x: x["score"], reverse=True)
            return candidates[0]["channel"]

        return None

    def is_channel_valid(self, channel_name: str) -> bool:
        """메타데이터를 확인하여 센서 고장이나 신뢰성 문제가 있는지 체크합니다."""
        channel = self.find_channel_by_name(channel_name)
        if not channel:
            return False
        
        props = channel.properties
        desc = (str(props.get("description", "")) + 
                str(props.get("INST_INSCOM", "")) + 
                str(props.get("COMMENT", ""))).upper()
        
        # 고장 또는 품질 불량 키워드 확인
        bad_keywords = ["FAIL", "QUESTION", "BAD", "ERROR"]
        if any(kw in desc for kw in bad_keywords):
            logger.warning(f"Channel {channel_name} marked as invalid in metadata: {desc[:50]}...")
            return False
        return True

    def preprocess_signal(
        self, time_s: np.ndarray, raw_g: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        # Bias Removal (Robust)
        # Exclude exact 0.0 (muted) samples from bias calculation
        is_active = (raw_g != 0.0)
        pre_impact_mask = (time_s < -0.005) & is_active
        
        offset = 0.0
        if np.sum(pre_impact_mask) > 10:
            offset = np.mean(raw_g[pre_impact_mask])
        else:
            # If no pre-impact active data, try first active samples
            active_indices = np.where(is_active)[0]
            if len(active_indices) > 0:
                first_active = active_indices[0]
                # If impact is far enough, use start of active signal
                # (Simple fallback for tests starting at 0)
                offset = np.mean(raw_g[first_active : first_active + 20])
        
        zeroed_g = raw_g - offset

        # Polarity Check (감속 = -G, 양수 피크면 반전)
        # A deceleration pulse's integral should be negative.
        # If the sum of the signal is positive, it's likely inverted.
        if np.sum(zeroed_g) > 0:
            zeroed_g = zeroed_g * -1

        return time_s, zeroed_g

    def get_clean_pulse_data(self, channel_name: Optional[str] = None) -> Dict:
        # Initialize result dictionary
        pulse_data_result = {}

        # Try to find the channel specified by name
        found_channel = None
        if channel_name:
            found_channel = self.find_channel_by_name(channel_name)
        
        # If specified channel not found, or no channel_name provided, try to find a suitable vehicle accel channel
        if not found_channel:
            found_channel = self.find_vehicle_accel_channel()
        
        if not found_channel:
            pulse_data_result["error"] = f"No suitable channel found for analysis (specified: {channel_name})."
            return pulse_data_result
        
        channel = found_channel
        props = channel.properties
        pulse_data_result["meta"] = props
        pulse_data_result["sensor_name"] = channel.name
        pulse_data_result["sensor_loc"] = props.get("INST_INSCOM") or props.get("SENLOCD", "Unknown")

        # Time Vector
        try:
            if "wf_increment" in props and "wf_start_offset" in props:
                dt = float(props["wf_increment"])
                t0 = float(props["wf_start_offset"])
                time_s = t0 + np.arange(len(channel)) * dt
                raw_g = channel[:]
            else:
                raw_g = channel[:]
                time_s = channel.time_track()
                dt = time_s[1] - time_s[0] if len(time_s) > 1 else 1e-4
            pulse_data_result["fs"] = 1.0 / dt
        except Exception:
            pulse_data_result["error"] = "Time vector construction failed"
            return pulse_data_result

        # Velocity (impact_velocity_kph)
        impact_velocity_kph = None
        speed_keys = ["INST_INIVEL", "TEST_CLSSPD", "VEH_VEHSPD", "CLOSING_SPEED"]
        for key in speed_keys:
            val = props.get(key)
            if val is None and self.tdms_file:
                val = self.tdms_file.properties.get(key)
            if val:
                try:
                    f_val = float(val)
                    if f_val > 1.0: # Only consider if value is realistic
                        impact_velocity_kph = f_val
                        break
                except ValueError:
                    continue
        pulse_data_result["impact_velocity_kph"] = impact_velocity_kph

        # Angle (impact_angle_deg)
        impact_angle = 0.0
        angle_keys = ["TEST_IMPANG", "IMPANG", "IMPACT_ANGLE"]
        for key in angle_keys:
            val = props.get(key)
            if val is None and self.tdms_file:
                val = self.tdms_file.properties.get(key)
            if val:
                try:
                    impact_angle = float(val)
                    break
                except ValueError:
                    continue
        pulse_data_result["impact_angle_deg"] = impact_angle

        # Truncate data to -50ms to 250ms range (allow pre-impact for bias removal)
        time_mask = (time_s >= -0.050) & (time_s <= 0.250)
        time_s = time_s[time_mask]
        raw_g = raw_g[time_mask]

        # If data points are too few after truncation, return an error, but with extracted metadata
        if len(time_s) < 10:
             pulse_data_result["error"] = "Not enough data points in the 0-150ms range."
             return pulse_data_result

        # Preprocess
        clean_time, clean_g = self.preprocess_signal(time_s, raw_g)
        
        pulse_data_result["time_s"] = clean_time
        pulse_data_result["accel_g"] = clean_g
        
        return pulse_data_result

