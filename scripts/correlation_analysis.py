"""
Final Correlation Analysis: Pulse Metrics vs Occupant Injury vs Vehicle Specs
"""

import sqlite3
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from config import settings


def analyze_correlation():
    conn = sqlite3.connect(settings.DB_PATH)

    # Pulse 결과 + 차량 정보 + 운전자 상해 정보를 모두 조인
    query = """
    SELECT 
        v.weight as 'Weight (kg)',
        p.peak_g as 'Peak G',
        p.olc_approx_g as 'OLC (G)',
        p.max_crush_mm as 'Dynamic Crush (mm)',
        p.total_energy_kj as 'Absorbed Energy (kJ)',
        o.hic as 'HIC',
        o.chest_deflection as 'Chest Deflection (mm)',
        o.femur_left as 'Femur Load (N)'
    FROM pulse_metrics p
    JOIN test_vehicles v ON p.test_no = v.test_no
    JOIN test_occupants o ON p.test_no = o.test_no
    WHERE o.seat_pos = 'CN'  -- 운전석 기준
      AND o.hic IS NOT NULL
      AND p.peak_g IS NOT NULL
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("[!] 데이터가 부족합니다. batch_analysis_with_db.py를 먼저 실행하세요.")
        return

    print(f"[*] 총 {len(df)}건의 데이터로 상관관계 분석을 수행합니다.")

    # 1. 상관관계 매트릭스 히트맵
    plt.figure(figsize=(12, 10))
    corr = df.corr()
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", vmin=-1, vmax=1)
    plt.title("Correlation Matrix: Crash Pulse vs Injury")
    plt.tight_layout()
    plt.show()

    # 2. 핵심 분석: 중량 vs OLC (물리 법칙 검증)
    plt.figure(figsize=(10, 6))
    sns.regplot(
        x="Weight (kg)",
        y="OLC (G)",
        data=df,
        scatter_kws={"alpha": 0.6},
        line_kws={"color": "red"},
    )
    plt.title("Vehicle Weight vs OLC (Occupant Load Criterion)")
    plt.grid(True)
    plt.show()

    # 3. 핵심 분석: OLC vs Chest Deflection (펄스 강도와 상해의 관계)
    plt.figure(figsize=(10, 6))
    sns.regplot(
        x="OLC (G)",
        y="Chest Deflection (mm)",
        data=df,
        scatter_kws={"alpha": 0.6},
        line_kws={"color": "red"},
    )
    plt.title("OLC vs Chest Injury")
    plt.grid(True)
    plt.show()


if __name__ == "__main__":
    analyze_correlation()
