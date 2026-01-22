from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    context_api_token: str
    version: str = "0.0.0"
    git_sha: str = "unknown"

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


settings = Settings()
