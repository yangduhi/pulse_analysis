import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from config import settings


def compare_static_vs_dynamic():
    conn = sqlite3.connect(settings.DB_PATH)

    # 정적 변형량(DPD_1)과 동적 변형량(pulse_metrics) 조인
    query = """
    SELECT 
        v.test_no,
        v.make,
        v.model,
        v.dpd_1 as static_crush_mm,      -- 정적 변형량 (메타데이터)
        p.max_crush_mm as dynamic_crush_mm -- 동적 변형량 (Pulse 적분값)
    FROM test_vehicles v
    JOIN pulse_metrics p ON v.test_no = p.test_no
    WHERE v.dpd_1 > 0 AND p.max_crush_mm > 0
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("[!] 비교할 데이터가 없습니다. 분석 스크립트를 먼저 실행하세요.")
        return

    # 시각화
    plt.figure(figsize=(10, 8))

    # 1:1 라인 (이 라인보다 위에 점이 찍혀야 함: Dynamic > Static)
    max_val = max(df["static_crush_mm"].max(), df["dynamic_crush_mm"].max())
    plt.plot([0, max_val], [0, max_val], "r--", label="Static = Dynamic Line")

    sns.scatterplot(data=df, x="static_crush_mm", y="dynamic_crush_mm", alpha=0.7)

    plt.title("Static Crush (Metadata) vs Dynamic Crush (Pulse Integration)")
    plt.xlabel("Static Crush (AX/BX Meta) [mm]")
    plt.ylabel("Max Dynamic Crush (from Pulse) [mm]")
    plt.grid(True)
    plt.legend()
    plt.show()


if __name__ == "__main__":
    compare_static_vs_dynamic()
