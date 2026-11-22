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
    embedding_provider: Literal["local", "semantic", "openai"] = "semantic"
    generation_provider: Literal["extractive", "openai"] = "extractive"
    embedding_dimensions: int = 384
    model_cache_dir: Path = Path("./data/models")
    model_local_files_only: bool = False
    embedding_batch_size: int = 32
    embedding_threads: int = 2
    embedding_cache_size: int = 2048
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    openai_model: str = ""
    job_lease_seconds: int = 300
    export_dir: Path = Path("./data/exports")
    export_max_source_mb: int = 100
    export_max_archive_mb: int = 80
    export_storage_mb: int = 512
    export_retention_seconds: int = 3600

    @property
    def origins(self) -> list[str]:
        return [x.strip().rstrip("/") for x in self.app_origins.split(",") if x.strip()]


@lru_cache
def settings() -> Settings:
    return Settings()
