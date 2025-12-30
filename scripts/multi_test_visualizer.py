"""
Multi-Test-Visualizer for NHTSA Crash Pulse Analysis.
Overlays plots of Acceleration, Velocity, and Displacement for all test cases
specified in a given CSV file to allow for comprehensive visual comparison.
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from tqdm import tqdm
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

def visualize_all_tests_from_csv(csv_path):
    """
    지정된 CSV 파일의 모든 테스트 케이스를 읽어 하나의 그래프에 오버레이하여 그립니다.
    [수정] 이상값(Max G > 100), 시간 범위(0-100ms), 축 범위/방향 필터링 기능 추가.
    """
    # 1. CSV 파일 로드 및 전처리
    if not os.path.exists(csv_path):
        print(f"[!] Error: '{csv_path}' not found.")
        return

    df = pd.read_csv(csv_path, dtype={'TestNo': str})
    df.dropna(subset=['TestNo', 'ChannelName'], inplace=True)
    df.rename(columns={'TestNo': 'test_no', 'ChannelName': 'channel_name'}, inplace=True)
    df['test_no'] = pd.to_numeric(df['test_no'], errors='coerce')
    df.dropna(subset=['test_no'], inplace=True)
    df['test_no'] = df['test_no'].astype(int)

    print(f"[*] Found {len(df)} test cases in '{csv_path}'. Processing...")

    # 2. 그래프 준비
    fig, axs = plt.subplots(3, 1, figsize=(12, 15), sharex=True)
    skipped_count = 0

    # 3. 모든 테스트 케이스를 순회하며 데이터 처리 및 플로팅
    for _, row in tqdm(df.iterrows(), total=len(df), desc="Visualizing Tests"):
        test_no = row['test_no']
        channel_name = row['channel_name']
        
        tdms_path = find_tdms_path(test_no)
        if not tdms_path:
            skipped_count += 1
            continue

        analyzer = CrashPulseAnalyzer(tdms_path)
        clean_data = analyzer.get_clean_pulse_data(channel_name=channel_name)

        if "error" in clean_data:
            skipped_count += 1
            continue

        # 이상값 처리: 최대 가속도 100G 초과 시 건너뛰기
        if np.max(np.abs(clean_data["accel_g"])) > 100:
            skipped_count += 1
            continue

        # 시간 범위 필터링 (0 ~ 100ms)
        time_s = clean_data["time_s"]
        accel_g = clean_data["accel_g"]
        time_filter_mask = (time_s >= 0) & (time_s <= 0.1)
        
        time_s_filtered = time_s[time_filter_mask]
        accel_g_filtered = accel_g[time_filter_mask]

        if len(time_s_filtered) == 0:
            skipped_count += 1
            continue
            
        v0 = clean_data.get("impact_velocity_kph")
        impact_mps = v0 / 3.6 if v0 else None

        signal = SignalProcessor.process(
            time_s_filtered,
            accel_g_filtered,
            cfc=60,
            known_impact_velocity_mps=impact_mps,
        )

        # 각 플롯에 데이터 추가 (낮은 alpha 값으로 투명도 설정)
        axs[0].plot(signal.time_ms, signal.filtered_accel_g, color="red", alpha=0.1)
        axs[1].plot(signal.time_ms, signal.velocity_kph, color="blue", alpha=0.1)
        axs[2].plot(signal.time_ms, signal.displacement_m * 1000, color="green", alpha=0.1)

    print(f"[*] Visualization complete. Skipped {skipped_count} tests (file not found, error, or outlier).")

    # 4. 최종 그래프 스타일 설정
    # (1) Acceleration
    axs[0].set_ylabel("Acceleration [G]")
    axs[0].set_title("Overlay of All Filtered Acceleration Traces (CFC60)")
    axs[0].grid(True)
    if axs[0].get_ylim()[1] > 20: # Make sure peak is negative
        axs[0].invert_yaxis()


    # (2) Velocity
    axs[1].set_ylabel("Velocity [km/h]")
    axs[1].set_title("Overlay of All Delta-V Profiles")
    axs[1].grid(True)
    axs[1].set_ylim(-60, 5) # Y축 범위 설정

    # (3) Displacement (Crush)
    axs[2].set_ylabel("Dynamic Crush [mm]")
    axs[2].set_xlabel("Time [ms]")
    axs[2].set_title("Overlay of All Dynamic Crush Profiles")
    axs[2].grid(True)
    
    # X축 범위 설정
    axs[2].set_xlim(0, 100)

    plt.suptitle(f"Composite Visualization from '{os.path.basename(csv_path)}' (0-100ms, Max 100G)", fontsize=16)
    plt.tight_layout(rect=[0, 0.03, 1, 0.97])
    plt.show()


if __name__ == "__main__":
    # 사용할 CSV 파일 경로
    target_csv = "matched_sensor_list.csv"
    visualize_all_tests_from_csv(target_csv)
