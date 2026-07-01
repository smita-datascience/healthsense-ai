"""Typed application settings, loaded from environment / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "HealthSense AI"
    environment: str = "development"

    # One knob switches SQLite <-> MySQL.
    database_url: str = "sqlite:///./healthsense.db"

    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-5"
    llm_provider: str = "anthropic"


settings = Settings()
