"""
Advanced Dynamic Metrics (OLC, Energy, Max Displacement)
"""

from typing import Any, Dict

import numpy as np

from src.analysis.core import CrashSignal

from .base import MetricStrategy


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
