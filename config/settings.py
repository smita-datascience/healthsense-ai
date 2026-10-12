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

    # --- WhatsApp Cloud API (v2) ---
    # From Meta: App > WhatsApp > API Setup ("Try it out" page)
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    # From Meta: App settings > Basic > App secret (used to verify signatures)
    whatsapp_app_secret: str = ""
    # A password YOU invent; paste the same text into Meta's webhook form.
    whatsapp_verify_token: str = ""
    whatsapp_api_version: str = "v25.0"


settings = Settings()
