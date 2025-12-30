# config.py
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    프로젝트 전역 설정 관리 (Pydantic V2)
    .env 파일에서 환경 변수를 로드하며, 없을 경우 기본값을 사용합니다.
    """

    # Project Info
    PROJECT_NAME: str = "Pulse_Analysis"
    VERSION: str = "1.0.0"

    # Storage Settings
    DATA_ROOT: str = "data"
    DB_PATH: str = os.path.join(DATA_ROOT, "nhtsa_data.db")
    LOG_DIR: str = "./logs"

    # Analysis Settings
    CFC_FILTER_CLASS: int = 60

    # .env 파일 로드 설정
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# 싱글톤 인스턴스 생성
settings = Settings()

# 디렉토리 자동 생성 (초기화 시점 실행)
os.makedirs(settings.DATA_ROOT, exist_ok=True)
os.makedirs(settings.LOG_DIR, exist_ok=True)
