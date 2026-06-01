from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://datalogue:datalogue@localhost:5432/datalogue"

    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = "https://api.minimaxi.com/v1"
    LLM_MODEL: str = "MiniMax-M2.7"

    SECRET_KEY: str = "change-me"
    AES_KEY: str = "your-32-byte-aes-key-here!!"

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
