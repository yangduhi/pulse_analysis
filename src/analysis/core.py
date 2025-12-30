"""
Core data structures for crash analysis.
"""

from dataclasses import dataclass
import numpy as np


@dataclass
class CrashSignal:
    """
    충돌 신호 데이터 컨테이너.
    이 객체 하나만 있으면 어떤 분석기(Metric)든 계산이 가능합니다.
    """

    time_ms: np.ndarray  # 시간 (ms)
    raw_accel_g: np.ndarray  # 원본 가속도 (G)
    filtered_accel_g: np.ndarray  # 필터링된 가속도 (G) - CFC 60
    velocity_kph: np.ndarray  # 속도 (km/h)
    displacement_m: np.ndarray  # 변위 (m)
    sample_rate: float  # 샘플링 레이트 (Hz)

    @property
    def dt(self) -> float:
        """Time step (seconds)"""
        return 1.0 / self.sample_rate
