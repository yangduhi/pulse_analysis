"""
Batch Crash Pulse Analysis Script.
Features:
1. Auto-Classification: Frontal, Side, Rear, Rollover based on metadata.
2. Physics-based Analysis: Uses V0 from metadata for accurate crush calculation.
3. Sanity Check: Filters out invalid crush data (> 2000mm).
4. Auto Schema Migration: Updates DB table automatically.
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


# --- [1] 분류 로직 함수 ---
def classify_category(crash_type: str, impact_angle_deg: float) -> str:
    """
    NHTSA 분류 기준에 따른 세부 카테고리(Sub-Category) 판별

    1. 정면 충돌 (Frontal): VEHICLE INTO BARRIER / VEHICLE, Angle 0 (+-30)
    2. 측면 충돌 (Side): IMPACTOR INTO VEHICLE (90/270), POLE
    3. 후방 충돌 (Rear): IMPACTOR INTO VEHICLE (180)
    4. 전복 (Rollover): ROLLOVER
    """
    ct = str(crash_type).upper()

    # 각도 정규화 (None일 경우 0 처리)
    try:
        angle = float(impact_angle_deg) % 360  # 0~360도로 정규화
    except (TypeError, ValueError):
        angle = 0.0

    # [4] 전복 시험 (Rollover)
    if "ROLLOVER" in ct:
        return "Rollover"

    # [1] 정면 충돌 (Frontal Impact)
    # 조건: Barrier 또는 Vehicle 충돌이면서, 각도가 0도 근처(±30도)
    # 0도 근처: 330~360 또는 0~30
    is_frontal_angle = (angle >= 330) or (angle <= 30)
    if ("BARRIER" in ct or "VEHICLE INTO VEHICLE" in ct) and is_frontal_angle:
        return "Frontal"

    # [2] 측면 충돌 (Side Impact)
    # 조건 A: Pole 충돌 (각도 무관하게 주로 측면)
    if "POLE" in ct:
        return "Side"

    # 조건 B: MDB(Impactor) 충돌이면서, 각도가 90도(우측) 또는 270도(좌측) 근처 (±30도)
    # 90도 근처: 60~120, 270도 근처: 240~300
    is_side_angle = (60 <= angle <= 120) or (240 <= angle <= 300)
    if "IMPACTOR" in ct and is_side_angle:
        return "Side"

    # [3] 후방 충돌 (Rear Impact)
    # 조건: MDB(Impactor) 충돌이면서, 각도가 180도 근처 (±30도)
    # 180도 근처: 150~210
    is_rear_angle = 150 <= angle <= 210
    if "IMPACTOR" in ct and is_rear_angle:
        return "Rear"

    # 그 외 (Off-set 충돌이나 특수 조건)
    return "Other"


# --- [2] DB 초기화 및 결과 저장 ---
def init_analysis_table():
    """
    분석 결과 테이블을 준비합니다.
    새로운 컬럼(sub_category 등)이 없으면 자동으로 테이블을 재생성합니다.
    """
    conn = sqlite3.connect(settings.DB_PATH)
    cursor = conn.cursor()

    # 1. 테이블 존재 여부 확인
    cursor.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='pulse_metrics'"
    )
    table_exists = cursor.fetchone()[0] > 0

    # 2. 스키마 검증 (테이블이 있을 경우)
    if table_exists:
        cursor.execute("PRAGMA table_info(pulse_metrics)")
        columns = [info[1] for info in cursor.fetchall()]

        # 필수 새 컬럼이 없으면 '구버전'으로 판단하고 삭제
        required_cols = ["impact_velocity_kph", "sensor_location", "sub_category"]
        if any(col not in columns for col in required_cols):
            print("[!] 구버전 DB 스키마 감지: 테이블을 재생성합니다 (새 컬럼 추가).")
            cursor.execute("DROP TABLE pulse_metrics")

    # 3. 테이블 생성 (새 스키마 적용)
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
            impact_velocity_kph REAL,  -- 실측 충돌 속도
            sensor_location TEXT,      -- 사용된 센서 위치
            sub_category TEXT,         -- [New] 자동 분류 결과 (Frontal, Side, etc.)
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(test_no) REFERENCES crash_tests(test_no)
        )
    """)
    conn.commit()
    conn.close()


def save_results_to_db(results_list):
    """분석 결과를 DB에 저장 (Batch Upsert)"""
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
                r.get("Impact_Velocity_Used_kph"),
                r.get("Sensor_Used"),
                r.get("Sub_Category"),  # [New]
            )
        )

    cursor.executemany(
        """
        INSERT OR REPLACE INTO pulse_metrics 
        (test_no, peak_g, time_at_peak_ms, delta_v_kph, max_crush_mm, 
         time_at_max_crush_ms, olc_approx_g, specific_energy_j_kg, total_energy_kj,
         impact_velocity_kph, sensor_location, sub_category)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        data,
    )

    conn.commit()
    conn.close()


# --- [3] 데이터 로드 및 유틸리티 ---
def get_ready_tests():
    conn = sqlite3.connect(settings.DB_PATH)
    # [중요] 모든 충돌 유형을 다 가져옵니다 (분류 로직 적용을 위해)
    query = """
    SELECT 
        t.test_no, t.year, t.make, t.model, t.crash_type, v.weight, q.filename
    FROM crash_tests t
    JOIN download_queue q ON t.test_no = q.test_no
    JOIN test_vehicles v ON t.test_no = v.test_no
    WHERE q.file_type = 'TDMS' 
      AND q.status = 'DONE'
      AND v.weight IS NOT NULL
    ORDER BY t.test_no DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def find_tdms_file(test_no, zip_filename):
    base_dir = os.path.join(settings.DATA_ROOT, "downloads", str(test_no))
    if not os.path.exists(base_dir):
        return None
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.lower().endswith(".tdms"):
                return os.path.join(root, f)
    return None


# --- [4] 메인 실행 함수 ---
def main():
    # 1. DB 초기화 (스키마 자동 업데이트)
    init_analysis_table()

    print("[*] Loading all test cases from DB...")
    df_tests = get_ready_tests()

    if df_tests.empty:
        print("[!] No ready tests found.")
        return

    print(f"[*] Found {len(df_tests)} tests. Starting Classification & Analysis...")

    # 2. 파이프라인 설정
    pipeline = CrashAnalysisPipeline()
    pipeline.add_metric(BasicKinematics())
    pipeline.add_metric(MaxDisplacement())
    pipeline.add_metric(OLCCalculator())
    pipeline.add_metric(EnergyAnalysis())

    results_buffer = []
    success_count = 0
    fail_count = 0

    # 3. 배치 분석 루프
    pbar = tqdm(df_tests.iterrows(), total=len(df_tests), unit="test")
    for _, row in pbar:
        test_no = row["test_no"]
        crash_type_db = row["crash_type"]  # DB 충돌 유형
        veh_weight = row["weight"]

        tdms_path = find_tdms_file(test_no, row["filename"])
        if not tdms_path:
            fail_count += 1
            continue

        # Pulse Analyzer 실행
        analyzer = CrashPulseAnalyzer(tdms_path)
        clean_data = analyzer.get_clean_pulse_data()

        if "error" in clean_data:
            fail_count += 1
            continue

        # [분류 실행] DB의 crash_type과 TDMS의 impact_angle 결합
        imp_angle = clean_data.get("impact_angle_deg", 0)
        category = classify_category(crash_type_db, imp_angle)

        # 메타데이터 추출된 속도
        impact_kph = clean_data.get("impact_velocity_kph")

        try:
            # 파이프라인 실행
            res = pipeline.run(
                time_data=clean_data["time_s"],
                accel_data=clean_data["accel_g"],
                vehicle_weight=veh_weight,
                impact_velocity_kph=impact_kph,
            )

            # [필터링] 2미터 이상 찌그러짐은 물리적 오류로 간주하고 Skip
            crush_mm = res.get("Max_Dynamic_Crush_mm", 0)
            if crush_mm > 2000 or crush_mm < 0:
                fail_count += 1
                continue

            # 결과 저장 준비
            res["test_no"] = test_no
            res["Sensor_Used"] = clean_data.get("sensor_loc", "Unknown")
            res["Sub_Category"] = category  # 분류 결과 저장

            results_buffer.append(res)
            success_count += 1

        except Exception:
            fail_count += 1
            continue

        # 50개마다 DB 저장
        if len(results_buffer) >= 50:
            save_results_to_db(results_buffer)
            results_buffer = []
            pbar.set_postfix({"Saved": success_count})

    # 남은 데이터 저장
    if results_buffer:
        save_results_to_db(results_buffer)

    print(f"\n[Done] Analysis & Classification Completed.")
    print(f"  - Success: {success_count}")
    print(f"  - Failed/Skipped: {fail_count}")


if __name__ == "__main__":
    main()
