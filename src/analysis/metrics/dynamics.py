"""
Advanced Dynamic Metrics (OLC, Energy, Max Displacement)
"""

import numpy as np
from typing import Dict, Any
from .base import MetricStrategy
from src.analysis.core import CrashSignal


class MaxDisplacement(MetricStrategy):
    """최대 변형량 (Dynamic Crush)"""

    def calculate(self, sig: CrashSignal) -> Dict[str, Any]:
        # 변위의 최대값 (보통 압축 방향)
        max_disp_m = np.max(np.abs(sig.displacement_m))
        time_at_max = sig.time_ms[np.argmax(np.abs(sig.displacement_m))]

        return {
            "Max_Dynamic_Crush_mm": round(max_disp_m * 1000, 1),
            "Time_at_Max_Crush_ms": round(time_at_max, 1),
        }


class EnergyAnalysis(MetricStrategy):
    """에너지 흡수 분석 (Energy Density)"""

    def calculate(self, sig: CrashSignal) -> Dict[str, Any]:
        mass = self.params.get("vehicle_mass", 0.0)

        # 가속도(m/s^2)
        accel_mps2 = sig.filtered_accel_g * 9.80665

        # Energy Density (Specific Energy) = Integral(|a| dx) [J/kg]
        # 변위(x)에 따른 가속도(a)의 적분 -> 단위 질량당 흡수 에너지
        specific_energy = np.trapz(np.abs(accel_mps2), sig.displacement_m)

        # 총 흡수 에너지 (Total Energy) = Specific Energy * Mass [kJ]
        total_energy_kj = (specific_energy * mass) / 1000.0 if mass > 0 else 0.0

        return {
            "Specific_Energy_Absorbed_J_kg": round(specific_energy, 2),
            "Total_Energy_Absorbed_kJ": round(total_energy_kj, 2),
        }


class OLCCalculator(MetricStrategy):
    """
    OLC (Occupant Load Criterion) 추정기
    약식 알고리즘: Free Flight 거리(예: 650mm 또는 0.065m 가상 변위) 도달 후
    나머지 구간의 평균 가속도.
    """

    def calculate(self, sig: CrashSignal) -> Dict[str, Any]:
        # 가상 더미 이동 거리 (보통 정면충돌 시 65mm ~ 300mm 사이 기준 사용)
        # 여기서는 약식으로 0~150ms 구간의 평균 가속도를 OLC 근사치로 사용하거나
        # 1차 피크 이후의 Plateau 구간을 찾습니다.

        # [구현] 단순화된 OLC: 유효 충돌 구간(속도가 0이 될 때까지)의 RMS 가속도
        valid_idx = (sig.time_ms >= 0) & (sig.time_ms <= 150)
        if not np.any(valid_idx):
            return {"OLC_Approx_G": 0.0}

        accel_segment = np.abs(sig.filtered_accel_g[valid_idx])

        # OLC는 보통 사각형 펄스에 근사시켰을 때의 높이
        # 여기서는 평균 가속도(Mean G)를 대용으로 제공
        mean_g = np.mean(accel_segment)

        return {"OLC_Approx_G": round(mean_g, 2)}
