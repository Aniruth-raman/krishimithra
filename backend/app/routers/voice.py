import uuid
import base64
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Conversation, Grievance
from app.schemas import VoiceTranscribeOut, VoiceSpeakRequest
from app.auth import get_current_user
from app.routers.chat import (
    detect_scheme_name,
    extract_tracking_id,
    format_grievance_tracking_result,
    format_scheme_result,
)
from app.config import settings
from app.services.ai.sarvam_ai_service import (
    chat_with_ai,
    check_scheme_eligibility,
    classify_intent,
    format_transcript_text,
    get_weather_advisory,
)
from app.services.ai.sarvam_service import transcribe_audio, text_to_speech
from app.services.location_extractor import extract_location

router = APIRouter(prefix="/voice", tags=["Voice"])

LANGUAGE_TO_AUDIO_CODE = {
    "ta": "ta-IN",
    "kn": "kn-IN",
    "hi": "hi-IN",
    "en": "en-IN",
    "ta-IN": "ta-IN",
    "kn-IN": "kn-IN",
    "hi-IN": "hi-IN",
    "en-IN": "en-IN",
}

AUDIO_TO_CHAT_LANGUAGE = {
    "ta-IN": "ta",
    "kn-IN": "kn",
    "hi-IN": "hi",
    "en-IN": "en",
}


def _audio_language(language: str) -> str:
    return LANGUAGE_TO_AUDIO_CODE.get(language, "en-IN")


def _chat_language(language: str) -> str:
    return AUDIO_TO_CHAT_LANGUAGE.get(_audio_language(language), language if language in {"ta", "kn", "hi", "en"} else "en")


def _farmer_context(user: User) -> dict:
    profile = user.farmer_profile
    if not profile:
        return {}
    return {
        "district": profile.district,
        "village": profile.village,
        "primary_crop": profile.primary_crop,
        "land_size": profile.land_size_acres,
        "state": profile.state,
        "farmer_category": profile.farmer_category,
        "annual_income": profile.annual_income,
    }


async def _read_text_payload(request: Request) -> tuple[str, str, str | None, bool]:
    content_type = request.headers.get("content-type", "")
    payload = {}
    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        payload = dict(form)
    elif "application/json" in content_type:
        payload = await request.json()
    else:
        form = await request.form()
        payload = dict(form) if form else dict(request.query_params)

    text = str(
        payload.get("text")
        or payload.get("message")
        or payload.get("transcript")
        or payload.get("query")
        or ""
    ).strip()
    if text.lower() in {"undefined", "null", "none"}:
        text = ""
    language = str(payload.get("language") or "en").strip()
    session_id_value = payload.get("session_id")
    session_id = str(session_id_value).strip() if session_id_value else None
    fast_response_value = payload.get("fast_response") or request.query_params.get("fast_response") or ""
    fast_response = str(fast_response_value).strip().lower() in {"1", "true", "yes", "on"}
    return text, language, session_id, fast_response


def _empty_voice_response(language: str, session_id: str) -> dict:
    chat_language = _chat_language(language)
    messages = {
        "ta": "உங்கள் குரல் தெளிவாக கேட்கவில்லை. தயவுசெய்து மைக்கிற்கு அருகில் மீண்டும் பேசுங்கள்.",
        "kn": "ನಿಮ್ಮ ಧ್ವನಿ ಸ್ಪಷ್ಟವಾಗಿ ಕೇಳಿಸಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮೈಕ್ ಹತ್ತಿರ ಮತ್ತೆ ಮಾತನಾಡಿ.",
        "hi": "आपकी आवाज साफ सुनाई नहीं दी। कृपया माइक्रोफोन के पास फिर से बोलें।",
        "en": "I could not hear that clearly. Please speak again closer to the microphone.",
    }


def _resolve_weather_location(message: str, context: dict) -> str | None:
    return (
        extract_location(message)
        or context.get("district")
        or context.get("village")
        or context.get("state")
    )


def _missing_location_message(language: str) -> str:
    messages = {
        "ta": "வானிலை அறிவுரைக்கு உங்கள் மாவட்டம் அல்லது நகரம் சொல்லுங்கள்.",
        "hi": "मौसम सलाह के लिए अपना जिला या शहर बताइए।",
        "kn": "ಹವಾಮಾನ ಸಲಹೆಗೆ ನಿಮ್ಮ ಜಿಲ್ಲೆ ಅಥವಾ ನಗರ ಹೇಳಿ.",
        "en": "Tell me your district or city for weather advice.",
    }
    return messages.get((language or "en").split("-")[0], messages["en"])
    return {
        "transcript": "",
        "response": "I missed that. Please say it once more, close to the microphone.",
        "intent": "voice",
        "session_id": session_id,
        "language": chat_language,
        "audio_language": _audio_language(language),
        "audio_base64": None,
        "audio_mime_type": None,
        "tts_available": False,
    }


async def _assistant_response(
    *,
    db: Session,
    current_user: User,
    message: str,
    language: str,
    session_id: str,
    voice_mode: bool = False,
) -> tuple[str, str]:
    history_records = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id, Conversation.session_id == session_id)
        .order_by(Conversation.created_at.asc())
        .limit(20)
        .all()
    )
    history = [{"role": record.role, "content": record.content} for record in history_records]
    tracking_id = extract_tracking_id(message)
    if tracking_id:
        grievance = db.query(Grievance).filter(Grievance.tracking_id.ilike(tracking_id)).first()
        response_text = format_grievance_tracking_result(grievance, tracking_id)
        intent = "grievance_track"
        db.add(Conversation(
            user_id=current_user.id,
            session_id=session_id,
            role="user",
            content=message,
            intent=intent,
            language=language,
        ))
        db.add(Conversation(
            user_id=current_user.id,
            session_id=session_id,
            role="assistant",
            content=response_text,
            intent=intent,
            language=language,
        ))
        db.commit()
        return response_text, intent

    intent = await classify_intent(message, fast=voice_mode)
    context = _farmer_context(current_user)

    if intent == "weather":
        location = _resolve_weather_location(message, context)
        if not location:
            response_text = _missing_location_message(language)
            db.add(Conversation(
                user_id=current_user.id,
                session_id=session_id,
                role="user",
                content=message,
                intent=intent,
                language=language,
            ))
            db.add(Conversation(
                user_id=current_user.id,
                session_id=session_id,
                role="assistant",
                content=response_text,
                intent=intent,
                language=language,
            ))
            db.commit()
            return response_text, intent
        response_text = await get_weather_advisory(
            crop_type=context.get("primary_crop") or "crop",
            district=location,
            query=message,
            language=language,
        )
    elif intent == "scheme":
        scheme_result = await check_scheme_eligibility(
            scheme_name=detect_scheme_name(message),
            state=context.get("state"),
            land_ownership="unknown",
            farmer_category=context.get("farmer_category"),
            annual_income=context.get("annual_income"),
            language=language,
        )
        response_text = format_scheme_result(scheme_result, language)
    else:
        response_text = await chat_with_ai(
            message=message,
            history=history,
            language=language,
            context=context if context else None,
            channel="voice" if voice_mode else "chat",
        )

    db.add(Conversation(
        user_id=current_user.id,
        session_id=session_id,
        role="user",
        content=message,
        intent=intent,
        language=language,
    ))
    db.add(Conversation(
        user_id=current_user.id,
        session_id=session_id,
        role="assistant",
        content=response_text,
        intent=intent,
        language=language,
    ))
    db.commit()
    return response_text, intent


@router.post("/transcribe", response_model=VoiceTranscribeOut)
async def transcribe(
    audio: UploadFile = File(...),
    language: str = Form("ta-IN"),
    current_user: User = Depends(get_current_user)
):
    """Convert speech audio to text using Sarvam AI STT."""
    if not audio.filename.lower().endswith((".wav", ".mp3", ".ogg", ".webm", ".m4a")):
        raise HTTPException(status_code=400, detail="Invalid audio format. Use WAV, MP3, OGG, WebM, or M4A.")

    content = await audio.read()
    if len(content) > 25 * 1024 * 1024:  # 25MB limit
        raise HTTPException(status_code=400, detail="Audio file too large. Max 25MB.")

    result = await transcribe_audio(content, language, audio.filename)
    chat_language = _chat_language(language)
    formatted_transcript = await format_transcript_text(result["transcript"], chat_language)
    return VoiceTranscribeOut(
        transcript=formatted_transcript,
        language=result["language"],
        confidence=result.get("confidence")
    )


@router.post("/speak")
async def speak(
    request: VoiceSpeakRequest,
    current_user: User = Depends(get_current_user)
):
    """Convert text to speech using Sarvam AI TTS."""
    if len(request.text) > 5000:
        raise HTTPException(status_code=400, detail="Text too long. Max 5000 characters.")

    audio_bytes = await text_to_speech(request.text, request.language)

    if audio_bytes:
        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={"Content-Disposition": "attachment; filename=speech.wav"}
        )
    else:
        # Return mock response info if TTS unavailable
        raise HTTPException(
            status_code=503,
            detail="Text-to-speech service unavailable. Configure SARVAM_API_KEY."
        )


@router.post("/conversation")
async def voice_conversation(
    audio: UploadFile = File(...),
    language: str = Form("en"),
    session_id: str | None = Form(None),
    fast_response: bool = Form(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One-shot browser voice assistant: audio -> Sarvam STT -> AI -> Sarvam TTS."""
    if not audio.filename.lower().endswith((".wav", ".mp3", ".ogg", ".webm", ".m4a")):
        raise HTTPException(status_code=400, detail="Invalid audio format. Use WAV, MP3, OGG, WebM, or M4A.")

    content = await audio.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Audio file too large. Max 25MB.")

    resolved_session_id = session_id or str(uuid.uuid4())
    audio_language = _audio_language(language)
    chat_language = _chat_language(language)

    transcription = await transcribe_audio(content, audio_language, audio.filename)
    raw_transcript = (transcription.get("transcript") or "").strip()
    if not raw_transcript:
        return _empty_voice_response(language, resolved_session_id)
    transcript = await format_transcript_text(raw_transcript, chat_language, use_ai=not fast_response)

    response_text, intent = await _assistant_response(
        db=db,
        current_user=current_user,
        message=transcript,
        language=chat_language,
        session_id=resolved_session_id,
        voice_mode=True,
    )

    tts_text = response_text[:650]
    audio_bytes = None if fast_response else await text_to_speech(tts_text, audio_language)
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8") if audio_bytes else None

    return {
        "transcript": transcript,
        "raw_transcript": raw_transcript,
        "response": response_text,
        "intent": intent,
        "session_id": resolved_session_id,
        "language": chat_language,
        "audio_language": audio_language,
        "audio_base64": audio_base64,
        "audio_mime_type": "audio/wav" if audio_base64 else None,
        "tts_available": bool(audio_base64),
    }


@router.post("/respond")
async def voice_text_response(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Respond to already-transcribed voice text and return Sarvam TTS audio."""
    text, language, session_id, fast_response = await _read_text_payload(request)
    resolved_session_id = session_id or str(uuid.uuid4())
    if not text:
        return _empty_voice_response(language, resolved_session_id)

    chat_language = _chat_language(language)
    audio_language = _audio_language(language)
    formatted_text = await format_transcript_text(text, chat_language, use_ai=not fast_response)
    if not formatted_text:
        return _empty_voice_response(language, resolved_session_id)

    response_text, intent = await _assistant_response(
        db=db,
        current_user=current_user,
        message=formatted_text,
        language=chat_language,
        session_id=resolved_session_id,
        voice_mode=True,
    )
    audio_bytes = None if fast_response else await text_to_speech(response_text[:650], audio_language)
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8") if audio_bytes else None

    return {
        "transcript": formatted_text,
        "response": response_text,
        "intent": intent,
        "session_id": resolved_session_id,
        "language": chat_language,
        "audio_language": audio_language,
        "audio_base64": audio_base64,
        "audio_mime_type": "audio/wav" if audio_base64 else None,
        "tts_available": bool(audio_base64),
    }


@router.post("/live/session")
async def live_voice_session(
    language: str = Form("en"),
    session_id: str | None = Form(None),
    current_user: User = Depends(get_current_user),
):
    """Bootstrap browser live voice. Uses Pipecat when configured, otherwise Sarvam turn loop."""
    resolved_session_id = session_id or str(uuid.uuid4())
    pipecat_url = settings.PIPECAT_BOT_URL.strip()
    provider = "pipecat" if pipecat_url else settings.VOICE_LIVE_FALLBACK
    return {
        "session_id": resolved_session_id,
        "provider": provider,
        "pipecat_url": pipecat_url or None,
        "fallback": settings.VOICE_LIVE_FALLBACK,
        "language": _chat_language(language),
        "audio_language": _audio_language(language),
        "sarvam": {
            "stt_model": settings.SARVAM_STT_MODEL,
            "llm_model": settings.SARVAM_CHAT_MODEL,
            "tts_model": settings.SARVAM_TTS_MODEL,
            "voice_id": settings.SARVAM_TTS_SPEAKER,
        },
        "instructions": "Use Pipecat client transport when pipecat_url is present; otherwise use /voice/conversation in live turn loop.",
    }
