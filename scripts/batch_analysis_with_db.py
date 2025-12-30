"""
Batch Crash Pulse Analysis Script (Production).
Process ALL downloaded files and save advanced metrics to SQLite.
"""

import os
import sqlite3
import pandas as pd
from tqdm import tqdm

from config import settings
from src.analysis.pulse import CrashPulseAnalyzer
from src.analysis.pipeline import CrashAnalysisPipeline
from src.analysis.metrics.kinematics import BasicKinematics
from src.analysis.metrics.dynamics import MaxDisplacement, EnergyAnalysis, OLCCalculator


def init_analysis_table():
    """분석 결과를 저장할 테이블 생성 (기존 DB 유지)"""
    conn = sqlite3.connect(settings.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pulse_metrics (
            test_no INTEGER PRIMARY KEY,
            peak_g REAL,
            time_at_peak_ms REAL,
            delta_v_kph REAL,
            max_crush_mm REAL,
            time_at_max_crush_ms REAL,
            olc_approx_g REAL,
            specific_energy_j_kg REAL,
            total_energy_kj REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(test_no) REFERENCES crash_tests(test_no)
        )
    """)
    conn.commit()
    conn.close()


def save_results_to_db(results_list):
    """분석 결과를 DB에 Upsert"""
    if not results_list:
        return

    conn = sqlite3.connect(settings.DB_PATH)
    cursor = conn.cursor()

    data = []
    for r in results_list:
        data.append(
            (
                r["test_no"],
                r.get("Peak_G"),
                r.get("Time_at_Peak_ms"),
                r.get("Delta_V_kph"),
                r.get("Max_Dynamic_Crush_mm"),
                r.get("Time_at_Max_Crush_ms"),
                r.get("OLC_Approx_G"),
                r.get("Specific_Energy_Absorbed_J_kg"),
                r.get("Total_Energy_Absorbed_kJ"),
            )
        )

    cursor.executemany(
        """
        INSERT OR REPLACE INTO pulse_metrics 
        (test_no, peak_g, time_at_peak_ms, delta_v_kph, max_crush_mm, 
         time_at_max_crush_ms, olc_approx_g, specific_energy_j_kg, total_energy_kj)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        data,
    )

    conn.commit()
    conn.close()
    print(f"[*] Saved {len(results_list)} analysis results to DB.")


def get_ready_tests():
    """
    [수정됨] matched_sensor_list.csv에서 TestNo와 ChannelName을 읽어 분석 대상을 결정합니다.
    - CSV 파일 로드 및 정리
    - DB에서 차량 무게(weight)와 TDMS 파일명(filename) 정보 가져오기
    - CSV 데이터와 DB 데이터를 병합하여 최종 분석 목록 생성
    """
    # 1. CSV 파일 로드 및 전처리
    csv_path = 'matched_sensor_list.csv'
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"'{csv_path}' 파일이 존재하지 않습니다.")

    df_csv = pd.read_csv(csv_path, dtype={'TestNo': str})
    df_csv.dropna(subset=['TestNo', 'ChannelName'], inplace=True)
    df_csv.rename(columns={'TestNo': 'test_no', 'ChannelName': 'channel_name'}, inplace=True)
    
    # test_no를 정수로 변환 시도 (오류 발생 시 해당 행 제외)
    df_csv['test_no'] = pd.to_numeric(df_csv['test_no'], errors='coerce')
    df_csv.dropna(subset=['test_no'], inplace=True)
    df_csv['test_no'] = df_csv['test_no'].astype(int)

    test_numbers = df_csv['test_no'].unique().tolist()
    if not test_numbers:
        return pd.DataFrame()

    # 2. DB에서 필요한 정보(weight, filename) 조회
    conn = sqlite3.connect(settings.DB_PATH)
    query = f"""
    SELECT 
        t.test_no, v.weight, q.filename
    FROM crash_tests t
    JOIN test_vehicles v ON t.test_no = v.test_no
    JOIN download_queue q ON t.test_no = q.test_no
    WHERE t.test_no IN ({','.join('?' for _ in test_numbers)})
      AND q.file_type = 'TDMS' 
      AND q.status = 'DONE'
      AND v.weight IS NOT NULL
    """
    df_db = pd.read_sql_query(query, conn, params=test_numbers)
    conn.close()

    # 3. CSV 데이터와 DB 데이터를 'test_no' 기준으로 병합
    df_merged = pd.merge(df_csv, df_db, on='test_no', how='inner')
    
    return df_merged


def find_tdms_file(test_no, zip_filename):
    base_dir = os.path.join(settings.DATA_ROOT, "downloads", str(test_no))
    if not os.path.exists(base_dir):
        return None
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.lower().endswith(".tdms"):
                return os.path.join(root, f)
    return None


def main():
    # 1. 결과 테이블 준비
    init_analysis_table()

    print("[*] Loading test cases from 'matched_sensor_list.csv'...")
    try:
        df_tests = get_ready_tests()
    except FileNotFoundError as e:
        print(f"[Error] {e}")
        return

    if df_tests.empty:
        print("[!] No ready tests found based on the CSV and DB.")
        return

    print(f"[*] Found {len(df_tests)} tests. Starting Batch Analysis...")

    # 파이프라인 설정
    pipeline = CrashAnalysisPipeline()
    pipeline.add_metric(BasicKinematics())
    pipeline.add_metric(MaxDisplacement())
    pipeline.add_metric(OLCCalculator())
    pipeline.add_metric(EnergyAnalysis())

    results_buffer = []

    # TQDM으로 진행률 표시
    for _, row in tqdm(df_tests.iterrows(), total=len(df_tests)):
        test_no = row["test_no"]
        veh_weight = row["weight"]
        channel_name = row["channel_name"]  # [수정됨] 사용할 채널 이름

        tdms_path = find_tdms_file(test_no, row.get("filename")) # filename이 없을 수 있음
        if not tdms_path:
            continue

        analyzer = CrashPulseAnalyzer(tdms_path)
        # [수정됨] 지정된 채널 이름으로 데이터 요청
        clean_data = analyzer.get_clean_pulse_data(channel_name=channel_name)

        if "error" in clean_data:
            # 에러 발생 시 건너뜀 (로그 생략하여 속도 향상)
            print(f"Failed TestNo: {test_no}, Channel: {channel_name}, Error: {clean_data['error']}")
            continue

        try:
            res = pipeline.run(
                time_data=clean_data["time_s"],
                accel_data=clean_data["accel_g"],
                vehicle_weight=veh_weight,
            )
            res["test_no"] = test_no
            results_buffer.append(res)
        except Exception as e:
            print(f"Analysis failed for TestNo: {test_no} with error: {e}")
            continue

        # 메모리 관리를 위해 50개마다 DB 저장
        if len(results_buffer) >= 50:
            save_results_to_db(results_buffer)
            results_buffer = []

    # 남은 데이터 저장
    if results_buffer:
        save_results_to_db(results_buffer)

    print("\n[Done] Batch analysis completed.")


if __name__ == "__main__":
    main()
