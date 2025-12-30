"""
Debug Visualizer for NHTSA Crash Pulse.
Plots Raw Accel, Velocity, and Displacement for a single test case.
Use this to diagnose why a specific file is failing or producing weird results.
"""

import os
import matplotlib.pyplot as plt
import numpy as np
from config import settings
from src.analysis.pulse import CrashPulseAnalyzer
from src.analysis.processing import SignalProcessor


def find_tdms_path(test_no):
    """테스트 번호로 TDMS 파일 경로 찾기"""
    base_dir = os.path.join(settings.DATA_ROOT, "downloads", str(test_no))
    if not os.path.exists(base_dir):
        return None
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.lower().endswith(".tdms"):
                return os.path.join(root, f)
    return None


def diagnose_test(test_no):
    print(f"\n{'=' * 50}")
    print(f"[*] Diagnosing Test #{test_no}...")

    # 1. 파일 찾기
    tdms_path = find_tdms_path(test_no)
    if not tdms_path:
        print(f"[!] Error: TDMS file not found for Test #{test_no}")
        return

    print(f"[*] File found: {os.path.basename(tdms_path)}")

    # 2. Pulse Analyzer 실행 (센서 찾기 및 메타데이터 추출)
    analyzer = CrashPulseAnalyzer(tdms_path)
    clean_data = analyzer.get_clean_pulse_data()

    if "error" in clean_data:
        print(f"[!] Analysis Failed: {clean_data['error']}")
        return

    # 3. 추출된 정보 출력
    print(f"[*] Selected Sensor: {clean_data['sensor_name']}")
    print(f"[*] Sensor Location: {clean_data['sensor_loc']}")
    v0 = clean_data.get("impact_velocity_kph")
    print(f"[*] Detected Impact Velocity (V0): {v0} km/h")

    # 4. 물리 연산 (Signal Processing)
    # V0가 없으면 None으로 들어감 -> 로직 내부에서 Max Delta V로 추정
    impact_mps = v0 / 3.6 if v0 else None

    signal = SignalProcessor.process(
        clean_data["time_s"],
        clean_data["accel_g"],
        cfc=60,
        known_impact_velocity_mps=impact_mps,
    )

    # 5. 그래프 그리기 (Visual Debugging)
    fig, axs = plt.subplots(3, 1, figsize=(10, 12), sharex=True)

    # (1) Acceleration
    axs[0].plot(
        signal.time_ms, signal.raw_accel_g, label="Raw", color="lightgray", alpha=0.7
    )
    axs[0].plot(
        signal.time_ms,
        signal.filtered_accel_g,
        label="CFC60 Filtered",
        color="red",
        linewidth=2,
    )
    axs[0].set_ylabel("Acceleration [G]")
    axs[0].set_title(
        f"Test #{test_no} - Acceleration (Sensor: {clean_data['sensor_name']})"
    )
    axs[0].legend()
    axs[0].grid(True)

    # (2) Velocity
    axs[1].plot(signal.time_ms, signal.velocity_kph, color="blue", linewidth=2)
    axs[1].set_ylabel("Velocity [km/h]")
    axs[1].set_title(f"Velocity Profile (V0 Used: {v0 if v0 else 'Estimated'} km/h)")
    axs[1].grid(True)

    # (3) Displacement (Crush)
    axs[2].plot(
        signal.time_ms, signal.displacement_m * 1000, color="green", linewidth=2
    )
    axs[2].set_ylabel("Dynamic Crush [mm]")
    axs[2].set_xlabel("Time [ms]")
    axs[2].set_title("Dynamic Crush (Displacement)")
    axs[2].grid(True)

    # 주요 수치 표시
    max_crush = np.max(signal.displacement_m * 1000)
    axs[2].annotate(
        f"Max: {max_crush:.1f} mm",
        xy=(signal.time_ms[np.argmax(signal.displacement_m)], max_crush),
        xytext=(10, -10),
        textcoords="offset points",
        arrowprops=dict(arrowstyle="->"),
    )

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    # 진단하고 싶은 테스트 번호를 여기에 입력하세요
    # 예: 실패했거나 그래프에서 이상하게 튀었던 번호
    target_test_no = 10000

    while True:
        try:
            val = input(f"Enter Test No (default {target_test_no}): ")
            if val.strip() == "":
                t_no = target_test_no
            else:
                t_no = int(val)

            diagnose_test(t_no)
        except ValueError:
            print("숫자를 입력하세요.")
        except KeyboardInterrupt:
            break
