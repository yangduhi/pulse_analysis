"""
Selective Batch Crash Pulse Analysis Script.

This script takes a CSV file containing a list of sensors (specified by
TestNo and ChannelName) as input, and runs the analysis pipeline only for
those selected sensors.

Usage:
    python run_selective_analysis.py <path_to_sensor_list.csv>
"""

import os
import sqlite3
import pandas as pd
from tqdm import tqdm
import argparse
import sys

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


def get_ready_tests(csv_path):
    """
    Reads TestNo and ChannelName from the provided CSV file to determine the analysis targets.
    - Loads and cleans the CSV file.
    - Retrieves vehicle weight and TDMS filename information from the database.
    - Merges the CSV data with the database data to create the final analysis list.
    """
    # 1. Load and preprocess the CSV file
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"The specified file was not found: '{csv_path}'")

    df_csv = pd.read_csv(csv_path, dtype={'TestNo': str}, on_bad_lines='skip')
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
    # 1. Set up argument parser
    parser = argparse.ArgumentParser(description="Run selective crash analysis based on a sensor list CSV.")
    parser.add_argument("csv_path", type=str, help="Path to the CSV file containing the list of sensors to analyze.")
    
    # Check if the user provided a csv_path
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    
    # 2. Prepare database and load test cases
    init_analysis_table()

    print(f"[*] Loading test cases from '{args.csv_path}'...")
    try:
        df_tests = get_ready_tests(args.csv_path)
    except FileNotFoundError as e:
        print(f"[Error] {e}")
        return

    if df_tests.empty:
        print("[!] No ready tests found based on the provided CSV and database records.")
        return

    print(f"[*] Found {len(df_tests)} tests. Starting Batch Analysis...")

    # 3. Configure and run the analysis pipeline
    pipeline = CrashAnalysisPipeline()
    pipeline.add_metric(BasicKinematics())
    pipeline.add_metric(MaxDisplacement())
    pipeline.add_metric(OLCCalculator())
    pipeline.add_metric(EnergyAnalysis())

    results_buffer = []

    for _, row in tqdm(df_tests.iterrows(), total=len(df_tests)):
        test_no = row["test_no"]
        veh_weight = row["weight"]
        channel_name = row["channel_name"]

        tdms_path = find_tdms_file(test_no, row.get("filename"))
        if not tdms_path:
            continue

        analyzer = CrashPulseAnalyzer(tdms_path)
        clean_data = analyzer.get_clean_pulse_data(channel_name=channel_name)

        if "error" in clean_data:
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

        if len(results_buffer) >= 50:
            save_results_to_db(results_buffer)
            results_buffer = []

    if results_buffer:
        save_results_to_db(results_buffer)

    print("\n[Done] Batch analysis completed.")


if __name__ == "__main__":
    main()
