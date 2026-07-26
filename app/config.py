from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    max_pages: int = 6
    max_chars_per_page: int = 8000
    request_timeout: float = 25.0
    user_agent: str = (
        "Mozilla/5.0 (compatible; TablixWebRAG/1.0; +https://tablix.ai) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
