"""
Base interface for all analysis metrics.
Strategy Pattern implementation.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from src.analysis.core import CrashSignal


class MetricStrategy(ABC):
    """모든 분석 메트릭의 부모 클래스"""

    # 일부 메트릭은 차량 중량 등이 필요할 수 있음
    def __init__(self, **kwargs):
        self.params = kwargs

    @abstractmethod
    def calculate(self, signal: CrashSignal) -> Dict[str, Any]:
        """신호를 받아 분석 결과를 딕셔너리로 반환"""
        pass
