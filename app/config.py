from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    context_api_token: str
    context_api_research_topic_key: str = "ai_research"
    context_postgres_data_dir: str = ""
    context_api_expect_persistent_corpus: bool = False
    context_api_expected_min_documents: int = 1
    version: str = "0.0.0"
    git_sha: str = "unknown"

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


settings = Settings()
