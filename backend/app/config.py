from pathlib import Path
from typing import Any, List
import json
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

    GEMINI_API_KEY: str = ""
    GEMINI_VISION_MODEL: str = "gemini-2.5-flash"
    INDIAN_CITIES_PATH: str = ""

    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    TWILIO_WHATSAPP_FROM: str = ""
    PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"
    PUBLIC_WEBHOOK_PREFIX: str = ""

    IVR_AGENT_NAME: str = "KrishiMitra"
    IVR_DEFAULT_LANGUAGE: str = "ta"
    IVR_ENABLED_LANGUAGES: str = "ta,kn,en"
    IVR_RESPONSE_MAX_CHARS: int = 650
    IVR_TWILIO_USE_SARVAM_AUDIO: bool = False

    PIPECAT_BOT_URL: str = ""
    PIPECAT_ICE_SERVERS: str = ""
    VOICE_LIVE_FALLBACK: str = "sarvam_loop"
    VOICE_ENABLE_AI_FORMATTING: bool = True

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

    @property
    def pipecat_ice_servers_list(self) -> List[dict[str, Any]]:
        if not self.PIPECAT_ICE_SERVERS.strip():
            return [{"urls": "stun:stun.l.google.com:19302"}]
        try:
            parsed = json.loads(self.PIPECAT_ICE_SERVERS)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
        return [{"urls": url.strip()} for url in self.PIPECAT_ICE_SERVERS.split(",") if url.strip()]


settings = Settings()

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

