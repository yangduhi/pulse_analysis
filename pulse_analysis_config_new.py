# config.py (for pulse_analysis project)
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    프로젝트 전역 설정 관리 (Pydantic V2)
    .env 파일에서 환경 변수를 로드하며, 없을 경우 기본값을 사용합니다.
    """

    # Project Info
    PROJECT_NAME: str = "Pulse_Analysis"
    VERSION: str = "1.0.0"

    # --- ETL 프로젝트 참조 설정 (Read-Only) ---
    # ETL 프로젝트(데이터 수집 및 DB)의 루트 경로를 정의합니다.
    # 환경 변수 'NHTSA_ETL_PATH'에서 읽어오거나, 기본값으로 현재 프로젝트의 형제 디렉토리 '../nhtsa'를 사용합니다.
    ETL_PROJECT_ROOT: Path = Path(os.getenv("NHTSA_ETL_PATH", Path(__file__).parents[1] / "nhtsa"))

    # ETL 프로젝트의 DB 경로
    # ETL_PROJECT_ROOT/data/nhtsa_data.db
    DB_PATH: Path = ETL_PROJECT_ROOT / "data" / "nhtsa_data.db"

    # ETL 프로젝트의 원본 다운로드 데이터 디렉토리 경로
    # ETL_PROJECT_ROOT/data/downloads
    RAW_DATA_DIR: Path = ETL_PROJECT_ROOT / "data" / "downloads"

    # --- 경로 유효성 검증 ---
    # DB 파일의 존재 여부를 확인합니다.
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB 파일이 존재하지 않습니다. ETL 프로젝트 위치를 확인하세요: {DB_PATH}")

    # RAW 데이터 디렉토리의 존재 여부를 확인합니다.
    if not RAW_DATA_DIR.exists():
        raise FileNotFoundError(f"원본 데이터 디렉토리가 존재하지 않습니다. ETL 프로젝트 위치를 확인하세요: {RAW_DATA_DIR}")

    # Analysis Settings
    CFC_FILTER_CLASS: int = 60

    # .env 파일 로드 설정
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# 싱글톤 인스턴스 생성
settings = Settings()

# 디렉토리 자동 생성 (초기화 시점 실행)
# 이 프로젝트 자체의 DATA_ROOT 및 LOG_DIR (아웃풋용)
os.makedirs("data", exist_ok=True)
os.makedirs("logs", exist_ok=True)
