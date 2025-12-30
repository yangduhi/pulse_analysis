# check_crash_types.py
import sqlite3
import pandas as pd
from config import settings


def check_types():
    conn = sqlite3.connect(settings.DB_PATH)

    print("=== [DB 내 충돌 유형(crash_type) 분포 확인] ===")

    # crash_type별 개수 조회
    query = """
    SELECT crash_type, count(*) as cnt 
    FROM crash_tests 
    GROUP BY crash_type 
    ORDER BY cnt DESC
    LIMIT 20
    """

    try:
        df = pd.read_sql_query(query, conn)
        if df.empty:
            print(
                "[!] crash_type 데이터가 비어있습니다. DB 저장 로직을 확인해야 합니다."
            )
        else:
            print(df.to_string(index=False))

    except Exception as e:
        print(f"오류 발생: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    check_types()
