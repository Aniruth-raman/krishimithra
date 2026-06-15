from pathlib import Path
from typing import List
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


APP_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=APP_DIR / ".env",
        env_file_encoding="utf-8-sig",
        case_sensitive=False,
        extra="ignore",
    )

    SECRET_KEY: str = "krishimitra-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    DATABASE_URL: str = "sqlite:///./krishimitra.db"

    SARVAM_API_KEY: str = ""
    SARVAM_CHAT_MODEL: str = "sarvam-105b"
    SARVAM_STT_MODEL: str = "saaras:v3"
    SARVAM_TTS_MODEL: str = "bulbul:v3"
    SARVAM_TTS_SPEAKER: str = "shubh"

    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"
    PUBLIC_WEBHOOK_PREFIX: str = ""

    IVR_AGENT_NAME: str = "KrishiMitra"
    IVR_DEFAULT_LANGUAGE: str = "ta"
    IVR_ENABLED_LANGUAGES: str = "ta,kn,en"
    IVR_RESPONSE_MAX_CHARS: int = 650
    IVR_TWILIO_USE_SARVAM_AUDIO: bool = False

    VOICE_ENABLE_AI_FORMATTING: bool = True
    VOICE_WEBRTC_ICE_SERVERS: str = "stun:stun.l.google.com:19302"
    VOICE_LIVE_SAMPLE_RATE: int = 16000

    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE: int = 10485760

    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def ivr_enabled_languages_list(self) -> List[str]:
        languages = [language.strip().lower() for language in self.IVR_ENABLED_LANGUAGES.split(",") if language.strip()]
        return languages or ["ta", "kn", "en"]


settings = Settings()

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

