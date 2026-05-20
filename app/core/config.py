from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # --- база ---
    DATABASE_URL: str
    DATABASE_URL_SYNC: str
    RIOT_API_KEY: str

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


# singleton
@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
