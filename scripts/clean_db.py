# reset_db_schema.py
import sqlite3
from config import settings


def reset_table():
    conn = sqlite3.connect(settings.DB_PATH)
    cursor = conn.cursor()

    print("[*] 기존 pulse_metrics 테이블 삭제 중...")
    cursor.execute("DROP TABLE IF EXISTS pulse_metrics")

    print("[*] 새로운 스키마로 테이블 재생성 중...")
    cursor.execute("""
        CREATE TABLE pulse_metrics (
            test_no INTEGER PRIMARY KEY,
            peak_g REAL,
            time_at_peak_ms REAL,
            delta_v_kph REAL,
            max_crush_mm REAL,
            time_at_max_crush_ms REAL,
            olc_approx_g REAL,
            specific_energy_j_kg REAL,
            total_energy_kj REAL,
            impact_velocity_kph REAL,  -- [New] 실측 충돌 속도
            sensor_location TEXT,      -- [New] 사용된 센서 위치
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(test_no) REFERENCES crash_tests(test_no)
        )
    """)

    conn.commit()
    conn.close()
    print("[Success] DB 스키마가 성공적으로 업데이트되었습니다.")


if __name__ == "__main__":
    reset_table()
