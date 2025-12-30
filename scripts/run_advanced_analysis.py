import os
import sqlite3
import numpy as np
import matplotlib.pyplot as plt
from nptdms import TdmsFile

# 우리가 만든 모듈들
from config import settings
from src.analysis.pulse import CrashPulseAnalyzer  # (이전 단계의 헬퍼 활용)
from src.analysis.pipeline import CrashAnalysisPipeline
from src.analysis.metrics.kinematics import BasicKinematics
from src.analysis.metrics.dynamics import MaxDisplacement, EnergyAnalysis, OLCCalculator


def get_tdms_path(test_no):
    """DB에서 다운로드된 TDMS 파일 경로 찾기"""
    base_dir = os.path.join(settings.DATA_ROOT, "downloads", str(test_no))
    if not os.path.exists(base_dir):
        return None

    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.lower().endswith(".tdms"):
                return os.path.join(root, f)
    return None


def main():
    # 1. 분석 대상 테스트 ID (DB에서 다운로드 완료된 것 중 하나 선택)
    # 예시: 6940, 7044 등 실제 다운로드된 ID를 입력하세요.
    target_test_id = 7044

    print(f"[*] Analyzing Test ID: {target_test_id}...")

    # 2. TDMS 파일 로드
    tdms_path = get_tdms_path(target_test_id)
    if not tdms_path:
        print("[!] TDMS file not found. Check download.py status.")
        return

    # 3. 채널 자동 탐색 (이전 단계의 헬퍼 클래스 재사용)
    finder = CrashPulseAnalyzer(tdms_path)
    channel = finder.find_vehicle_accel_channel()

    if not channel:
        print("[!] Suitable accelerometer channel not found.")
        return

    print(f"[*] Channel Found: {channel.name} ({channel.properties.get('SENLOCD')})")

    # Raw Data 추출
    time_seq = channel.time_track()
    accel_g = channel[:]

    # 차량 중량 (DB에서 가져와야 하지만 여기선 2000kg 가정)
    veh_weight = 2000.0

    # 4. 분석 파이프라인 구성 (레고 조립)
    pipeline = CrashAnalysisPipeline()
    pipeline.add_metric(BasicKinematics())
    pipeline.add_metric(MaxDisplacement())
    pipeline.add_metric(OLCCalculator())
    pipeline.add_metric(EnergyAnalysis(vehicle_mass=veh_weight))

    # 5. 실행
    results = pipeline.run(time_seq, accel_g, vehicle_weight=veh_weight)

    # 6. 결과 출력
    print("\n=== Analysis Results ===")
    for k, v in results.items():
        if k != "signal_obj":
            print(f"  - {k}: {v}")

    # 7. 시각화 (선택)
    sig = results["signal_obj"]
    plt.figure(figsize=(10, 6))
    plt.plot(sig.time_ms, sig.filtered_accel_g, label="CFC 60 Filtered G")
    plt.title(f"Crash Pulse (Test {target_test_id})")
    plt.xlabel("Time (ms)")
    plt.ylabel("Acceleration (G)")
    plt.grid(True)
    plt.legend()
    plt.xlim(0, 200)
    plt.show()


if __name__ == "__main__":
    main()
