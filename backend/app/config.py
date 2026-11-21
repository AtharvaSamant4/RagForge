from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    brand_name: str = "RAGForge"
    database_url: str = "sqlite:///./data/ragforge.db"
    storage_dir: Path = Path("./data/uploads")
    app_origins: str = "http://localhost:3000"
    cookie_secure: bool = False
    allow_registration: bool = True
    max_upload_mb: int = 20
    max_extracted_chars: int = 2_000_000
    rate_limit_per_minute: int = 60
    embedding_provider: Literal["local", "openai"] = "local"
    generation_provider: Literal["extractive", "openai"] = "extractive"
    embedding_dimensions: int = 384
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    openai_model: str = ""
    job_lease_seconds: int = 300

    @property
    def origins(self) -> list[str]:
        return [x.strip().rstrip("/") for x in self.app_origins.split(",") if x.strip()]


@lru_cache
def settings() -> Settings:
    return Settings()
