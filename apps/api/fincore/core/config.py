from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FINCORE_", env_file=".env", extra="ignore")

    env: str = "development"
    database_url: str = "sqlite:///./fincore.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "development-only-secret-change-me-32-chars"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "api", "testserver"]
    )
    provider_mode: str = "development"
    webhook_worker_enabled: bool = True
    max_request_bytes: int = 1_048_576
    rate_limit_per_minute: int = 120

    @field_validator("cors_origins", "allowed_hosts", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache

def get_settings() -> Settings:
    return Settings()
