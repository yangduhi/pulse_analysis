"""
Analysis Pipeline Manager.
Updated to accept 'impact_velocity_kph' for physics-based processing.
"""

from typing import List, Dict, Any
from src.analysis.processing import SignalProcessor
from src.analysis.metrics.base import MetricStrategy


class CrashAnalysisPipeline:
    def __init__(self):
        self.metrics: List[MetricStrategy] = []

    def add_metric(self, metric: MetricStrategy):
        self.metrics.append(metric)

    def run(
        self, time_data, accel_data, vehicle_weight=None, impact_velocity_kph=None
    ) -> Dict[str, Any]:
        """
        데이터를 받아 신호 처리 후 등록된 메트릭을 계산합니다.

        :param impact_velocity_kph: 메타데이터에서 추출한 실측 충돌 속도 (Physics Correction용)
        """
        # km/h -> m/s 변환 (값이 있을 경우에만)
        impact_v_mps = impact_velocity_kph / 3.6 if impact_velocity_kph else None

        # 1. 신호 처리 (Signal Processing)
        # 여기서 실측 속도(impact_v_mps)를 넘겨주어야 정확한 변위 적분이 가능합니다.
        signal = SignalProcessor.process(
            time_data, accel_data, cfc=60, known_impact_velocity_mps=impact_v_mps
        )

        results = {
            "signal_obj": signal,
            "Impact_Velocity_Used_kph": round(impact_v_mps * 3.6, 2)
            if impact_v_mps
            else "Estimated",
        }

        # 2. 메트릭 계산 (Metric Calculation)
        for metric in self.metrics:
            # 메트릭에 차량 중량 정보 주입
            if hasattr(metric, "mass") and vehicle_weight:
                metric.params["vehicle_mass"] = vehicle_weight

            try:
                metric_res = metric.calculate(signal)
                results.update(metric_res)
            except Exception as e:
                results[f"Error_{metric.__class__.__name__}"] = str(e)

        return results
