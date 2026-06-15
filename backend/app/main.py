from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine, ensure_sqlite_schema_compatibility
from app.routers import admin, auth, chat, disease, grievance, ivr, officer, scheme, voice, weather, whatsapp
from app.services.ai.sarvam_ai_service import diagnose_sarvam


Base.metadata.create_all(bind=engine)
ensure_sqlite_schema_compatibility()

app = FastAPI(
    title="KrishiMitra API",
    description="Backend API for farmer assistance, schemes, grievances, disease detection, chat, and voice services.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
app.mount("/client/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="client-uploads")

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(disease.router)
app.include_router(grievance.router)
app.include_router(scheme.router)
app.include_router(voice.router)
app.include_router(weather.router)
app.include_router(whatsapp.router)
app.include_router(ivr.router)
app.include_router(ivr.router, prefix="/api")
app.include_router(ivr.router, prefix="/client")
app.include_router(ivr.router, prefix="/client/api")
app.include_router(officer.router)
app.include_router(admin.router)


@app.on_event("startup")
async def warmup_services():
    print("Starting KrishiMitra service warm-up...")
    try:
        if settings.SARVAM_API_KEY:
            result = await diagnose_sarvam()
            print(f"Sarvam warm-up: {'ok' if result.get('ok') else result.get('message')}")
        else:
            print("Sarvam warm-up skipped: SARVAM_API_KEY is not configured.")
    except Exception as error:
        print(f"Sarvam warm-up failed: {error}")
    print("KrishiMitra warm-up complete.")


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "ai_provider": "sarvam",
        "sarvam_configured": bool(settings.SARVAM_API_KEY),
        "sarvam_chat_model": settings.SARVAM_CHAT_MODEL,
        "sarvam_stt_model": settings.SARVAM_STT_MODEL,
        "sarvam_tts_model": settings.SARVAM_TTS_MODEL,
        "sarvam_tts_speaker": settings.SARVAM_TTS_SPEAKER,
        "gemini_vision_configured": bool(settings.GEMINI_API_KEY),
        "gemini_vision_model": settings.GEMINI_VISION_MODEL,
        "voice_provider": "sarvam",
        "twilio_from_number": settings.TWILIO_FROM_NUMBER,
        "twilio_whatsapp_from": settings.TWILIO_WHATSAPP_FROM,
        "whatsapp_webhook": f"{settings.PUBLIC_BASE_URL.rstrip('/')}/whatsapp/webhook",
        "public_webhook_base": f"{settings.PUBLIC_BASE_URL.rstrip('/')}/{settings.PUBLIC_WEBHOOK_PREFIX.strip('/')}".rstrip("/"),
        "ivr_agent_name": settings.IVR_AGENT_NAME,
        "ivr_default_language": settings.IVR_DEFAULT_LANGUAGE,
        "ivr_enabled_languages": settings.ivr_enabled_languages_list,
        "ivr_twilio_use_sarvam_audio": settings.IVR_TWILIO_USE_SARVAM_AUDIO,
        "voice_live_provider": "pipecat" if settings.PIPECAT_BOT_URL else settings.VOICE_LIVE_FALLBACK,
        "pipecat_configured": bool(settings.PIPECAT_BOT_URL),
        "voice_ai_formatting": settings.VOICE_ENABLE_AI_FORMATTING,
    }


@app.get("/client/health")
async def client_health_check():
    return await health_check()


@app.get("/health/ai")
async def ai_health_check():
    return await diagnose_sarvam()


@app.post("/twilio/error")
async def twilio_error_webhook(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "").lower()
    payload: dict[str, Any] = {}
    try:
        if "application/json" in content_type:
            payload = await request.json()
        else:
            form = await request.form()
            payload = dict(form)
    except Exception as error:
        raw = (await request.body())[:2000]
        print("[TWILIO DEBUGGER RAW]", raw)
        print("[TWILIO DEBUGGER PARSE ERROR]", error)

    print("[TWILIO DEBUGGER PAYLOAD]", payload)
    return {"status": "received"}

