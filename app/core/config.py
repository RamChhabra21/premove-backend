from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str  # Reads from .env

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="allow"
    )

settings = Settings()  # Global config object