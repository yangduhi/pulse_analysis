"""
Basic Kinematic Metrics (Peak G, Delta V, etc.)
"""

import numpy as np
from typing import Dict, Any
from .base import MetricStrategy
from src.analysis.core import CrashSignal


class BasicKinematics(MetricStrategy):
    def calculate(self, sig: CrashSignal) -> Dict[str, Any]:
        # 유효 구간 설정 (0 ~ 300ms)
        valid_mask = (sig.time_ms >= 0) & (sig.time_ms <= 300)

        if not np.any(valid_mask):
            return {"Error": "No data in 0-300ms range"}

        accel_valid = sig.filtered_accel_g[valid_mask]
        vel_valid = sig.velocity_kph[valid_mask]

        # 1. Peak G (절대값 최대)
        peak_g = np.max(np.abs(accel_valid))
        time_at_peak = sig.time_ms[valid_mask][np.argmax(np.abs(accel_valid))]

        # 2. Delta V (최대 속도 변화량)
        # 일반적으로 충돌 초기 속도(0)에서 가장 크게 변한 지점
        delta_v = np.max(np.abs(vel_valid))

        return {
            "Peak_G": round(peak_g, 2),
            "Time_at_Peak_ms": round(time_at_peak, 1),
            "Delta_V_kph": round(delta_v, 2),
        }
