"""
Sarvam AI Service - Speech-to-Text and Text-to-Speech
Supports Tamil and Kannada languages.
"""
import httpx
import base64
from typing import Optional
from app.config import settings

SARVAM_BASE_URL = "https://api.sarvam.ai"

LANGUAGE_CODE_MAP = {
    "ta": "ta-IN",
    "kn": "kn-IN",
    "hi": "hi-IN",
    "en": "en-IN",
    "ta-IN": "ta-IN",
    "kn-IN": "kn-IN",
    "hi-IN": "hi-IN",
    "en-IN": "en-IN",
}


async def transcribe_audio(audio_bytes: bytes, language: str = "ta-IN", filename: str = "audio.wav") -> dict:
    """
    Convert speech to text using Sarvam AI STT API.
    Falls back to mock if API key not configured.
    """
    lang_code = LANGUAGE_CODE_MAP.get(language, "ta-IN")

    if not settings.SARVAM_API_KEY:
        return _mock_transcription(lang_code)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{SARVAM_BASE_URL}/speech-to-text",
                headers={"api-subscription-key": settings.SARVAM_API_KEY},
                files={"file": (filename, audio_bytes, _guess_audio_mime_type(filename))},
                data={
                    "language_code": lang_code,
                    "model": settings.SARVAM_STT_MODEL,
                    "mode": "transcribe",
                },
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    "transcript": data.get("transcript", ""),
                    "language": lang_code,
                    "confidence": data.get("confidence", 0.9)
                }
            print(f"Sarvam STT failed {response.status_code}: {response.text}")
            return _mock_transcription(lang_code)
    except Exception as error:
        print(f"Sarvam STT exception: {error}")
        return _mock_transcription(lang_code)


async def text_to_speech(text: str, language: str = "ta-IN", speaker: Optional[str] = None) -> Optional[bytes]:
    """
    Convert text to speech using Sarvam AI TTS API.
    Returns audio bytes or None if unavailable.
    """
    lang_code = LANGUAGE_CODE_MAP.get(language, "ta-IN")

    if not settings.SARVAM_API_KEY:
        return None

    selected_speaker = speaker or settings.SARVAM_TTS_SPEAKER

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{SARVAM_BASE_URL}/text-to-speech",
                headers={
                    "api-subscription-key": settings.SARVAM_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "text": text[:1000],
                    "target_language_code": lang_code,
                    "speaker": selected_speaker,
                    "pace": 1.0,
                    "speech_sample_rate": 22050,
                    "enable_preprocessing": True,
                    "model": settings.SARVAM_TTS_MODEL,
                }
            )
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "").lower()
                if "audio" in content_type:
                    return response.content
                data = response.json()
                audio_b64 = _extract_audio_base64(data)
                if audio_b64:
                    return base64.b64decode(_strip_data_uri(audio_b64))
            print(f"Sarvam TTS failed {response.status_code}: {response.text}")
        return None
    except Exception as error:
        print(f"Sarvam TTS exception: {error}")
        return None


def _extract_audio_base64(payload: dict) -> Optional[str]:
    if isinstance(payload.get("audio"), str):
        return payload["audio"]
    if isinstance(payload.get("audioContent"), str):
        return payload["audioContent"]
    if isinstance(payload.get("audio_base64"), str):
        return payload["audio_base64"]
    audios = payload.get("audios")
    if isinstance(audios, list) and audios:
        first_audio = audios[0]
        if isinstance(first_audio, str):
            return first_audio
        if isinstance(first_audio, dict):
            return _extract_audio_base64(first_audio)
    if isinstance(payload.get("data"), dict):
        return _extract_audio_base64(payload["data"])
    return None


def _strip_data_uri(audio_b64: str) -> str:
    return audio_b64.split(",", 1)[1] if audio_b64.startswith("data:") and "," in audio_b64 else audio_b64


def _guess_audio_mime_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".mp3"):
        return "audio/mpeg"
    if lower.endswith(".ogg"):
        return "audio/ogg"
    if lower.endswith(".webm"):
        return "audio/webm"
    if lower.endswith(".m4a"):
        return "audio/mp4"
    return "audio/wav"


async def translate_text(text: str, source_lang: str = "ta-IN", target_lang: str = "en-IN") -> str:
    """
    Translate text using Sarvam AI translation API.
    """
    if not settings.SARVAM_API_KEY:
        return text

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{SARVAM_BASE_URL}/translate",
                headers={
                    "api-subscription-key": settings.SARVAM_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "input": text,
                    "source_language_code": source_lang,
                    "target_language_code": target_lang,
                    "speaker_gender": "Female",
                    "mode": "formal",
                    "model": "mayura:v1",
                    "enable_preprocessing": False
                }
            )
            if response.status_code == 200:
                return response.json().get("translated_text", text)
        return text
    except Exception:
        return text


def _mock_transcription(lang_code: str) -> dict:
    """Mock transcription for demo purposes."""
    samples = {
        "ta-IN": "என் பயிரில் நோய் இருக்கிறது, என்ன செய்வது?",
        "kn-IN": "ನನ್ನ ಬೆಳೆಗೆ ರೋಗ ಇದೆ, ಏನು ಮಾಡಬೇಕು?",
        "hi-IN": "मेरी फसल में बीमारी है, मुझे क्या करना चाहिए?",
        "en-IN": "My crop has disease, what should I do?",
    }
    return {
        "transcript": samples.get(lang_code, "My crop needs help."),
        "language": lang_code,
        "confidence": 0.95,
    }

