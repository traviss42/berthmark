"""Application configuration using pydantic-settings."""

from functools import lru_cache
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General app settings
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Security & Auth
    SECRET_KEY: str = "berthmark-development-secret-key-change-in-production"
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"

    # External APIs & Datasets
    OPENMETEO_BASE_URL: str = "https://marine-api.open-meteo.com/v1/marine"
    AISSTREAM_API_KEY: str = ""
    AISSTREAM_BASE_URL: str = "https://api.aisstream.io/v1"
    PORTS_API_BASE_URL: str = "https://raw.githubusercontent.com/datasets/un-locode/master"
    UNLOCODE_DB_PATH: str = "backend/data/unlocode.db"
    UNLOCODE_SEED_PATH: str = "backend/data/maritime_ports.json"

    # HTTP Client Configuration
    HTTP_TIMEOUT_SECONDS: float = Field(default=5.0, ge=1.0, le=60.0)

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
