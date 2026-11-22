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
    deployment_mode: Literal["development", "private_alpha"] = "development"
    registration_mode: Literal["development", "invite", "disabled"] = "development"
    session_ttl_seconds: int = 604800
    api_key_ttl_days: int = 90
    max_projects_per_user: int = 100
    max_documents_per_project: int = 100
    user_storage_mb: int = 512
    max_ingestion_jobs_per_user: int = 20
    max_ingestion_processes: int = 4
    max_export_jobs_per_user: int = 2
    parser_wall_seconds: float = 15
    parser_cpu_seconds: int = 10
    parser_memory_mb: int = 512
    parser_output_mb: int = 16
    parser_require_sandbox: bool = False
    hosted_daily_requests: int = 100
    hosted_daily_input_chars: int = 200000
    hosted_call_input_chars: int = 64000
    allow_public_widgets: bool = True

    @property
    def origins(self) -> list[str]:
        return [x.strip().rstrip("/") for x in self.app_origins.split(",") if x.strip()]


@lru_cache
def settings() -> Settings:
    return Settings()
