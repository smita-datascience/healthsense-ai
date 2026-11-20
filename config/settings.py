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

    # --- Voice notes: speech-to-text (OpenAI) ---
    # Claude cannot take audio input, so voice notes are transcribed first,
    # then the TEXT goes through the same safety gates as a typed message.
    openai_api_key: str = ""
    # gpt-transcribe is OpenAI's recommended model; whisper-1 and the
    # gpt-4o-*-transcribe models are deprecated (shut down 26 Feb 2027).
    stt_model: str = "gpt-transcribe"


settings = Settings()