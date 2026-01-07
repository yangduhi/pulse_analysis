"""
Analysis Pipeline Manager.
Updated to accept 'impact_velocity_kph' for physics-based processing.
"""

import os
import sqlite3
import pandas as pd
from typing import List, Dict, Any, Optional
from loguru import logger # Add logger import

from config import settings # Add settings import
from src.analysis.processing import SignalProcessor
from src.analysis.metrics.base import MetricStrategy


class CrashAnalysisPipeline:
    def __init__(self):
        self.metrics: List[MetricStrategy] = []

    def add_metric(self, metric: MetricStrategy):
        self.metrics.append(metric)

    def run(
        self, time_data, accel_data, vehicle_weight=None, impact_velocity_kph=None, test_no: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        데이터를 받아 신호 처리 후 등록된 메트릭을 계산합니다.

        :param impact_velocity_kph: 메타데이터에서 추출한 실측 충돌 속도 (Physics Correction용).
                                    None이면 nhtsa_data_frontal.db에서 조회 시도.
        :param test_no: nhtsa_data_frontal.db에서 초기 속도를 조회하기 위한 테스트 번호.
        """
        
        final_impact_velocity_kph = impact_velocity_kph

        # impact_velocity_kph가 None이면 nhtsa_data_frontal.db에서 조회 시도
        if final_impact_velocity_kph is None and test_no is not None:
            frontal_db_path = os.path.join(settings.DATA_ROOT, "nhtsa_data_frontal.db")
            if os.path.exists(frontal_db_path):
                try:
                    conn = sqlite3.connect(frontal_db_path)
                    # frontal_crash_metadata 테이블에서 impact_velocity_kph 조회
                    query = f"SELECT impact_velocity_kph FROM frontal_crash_metadata WHERE test_no = ?"
                    df_vel = pd.read_sql_query(query, conn, params=(test_no,))
                    if not df_vel.empty and pd.notna(df_vel['impact_velocity_kph'].iloc[0]):
                        final_impact_velocity_kph = df_vel['impact_velocity_kph'].iloc[0]
                    conn.close()
                except Exception as e:
                    logger.warning(f"Failed to query nhtsa_data_frontal.db for TestNo {test_no}: {e}")

        # km/h -> m/s 변환 (값이 있으면)
        # 모든 메타데이터에서 초기 속도를 찾지 못하면 56kph로 폴백
        impact_v_mps = None
        if final_impact_velocity_kph is not None:
            impact_v_mps = final_impact_velocity_kph / 3.6
        else: # If still None after all lookups, fallback to 56 kph
            impact_v_mps = 56.0 / 3.6 # 56 kph fallback
        
        # 1. 신호 처리 (Signal Processing)
        # 여기서 실측 속도(impact_v_mps)를 넘겨주어야 정확한 변위 적분이 가능합니다.
        signal = SignalProcessor.process(
            time_data, accel_data, cfc=60, known_impact_velocity_mps=impact_v_mps
        )

        results = {
            "signal_obj": signal,
            "Impact_Velocity_Used_kph": round(impact_v_mps * 3.6, 2)
            if impact_v_mps is not None # Check for None before rounding
            else "Estimated (56 kph fallback)", # Indicate fallback
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
