import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.auth import get_current_user
from app.config import settings
from app.models import User
from app.routers.voice import _audio_language, _chat_language
from app.services.voice.live_pipecat import run_live_bot


router = APIRouter(prefix="/voice/live", tags=["Live Voice"])
_small_webrtc_handler: Any | None = None


def _pipecat_imports() -> tuple[Any, Any, Any]:
    try:
        from pipecat.transports.smallwebrtc.request_handler import (
            SmallWebRTCPatchRequest,
            SmallWebRTCRequest,
            SmallWebRTCRequestHandler,
        )
    except ImportError as error:
        raise HTTPException(
            status_code=503,
            detail="Pipecat WebRTC dependencies are not installed. Run: pip install 'pipecat-ai[sarvam,silero,webrtc]>=0.0.105'",
        ) from error
    return SmallWebRTCRequest, SmallWebRTCPatchRequest, SmallWebRTCRequestHandler


def _handler() -> Any:
    global _small_webrtc_handler
    _, _, SmallWebRTCRequestHandler = _pipecat_imports()
    if _small_webrtc_handler is None:
        from aiortc import RTCIceServer

        ice_servers = [
            RTCIceServer(urls=server.strip())
            for server in settings.VOICE_WEBRTC_ICE_SERVERS.split(",")
            if server.strip()
        ]
        _small_webrtc_handler = SmallWebRTCRequestHandler(ice_servers=ice_servers or None)
    return _small_webrtc_handler


async def _payload(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        return await request.json()
    if "form" in content_type:
        return dict(await request.form())
    return dict(request.query_params)


@router.post("/session")
async def create_live_voice_session(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    payload = await _payload(request)
    session_id = str(payload.get("session_id") or uuid.uuid4())
    language = _chat_language(str(payload.get("language") or "en"))
    return {
        "session_id": session_id,
        "provider": "pipecat-smallwebrtc",
        "webrtcUrl": str(request.url_for("live_voice_offer")),
        "connection_url": str(request.url_for("live_voice_offer")),
        "language": language,
        "audio_language": _audio_language(language),
        "ice_servers": settings.VOICE_WEBRTC_ICE_SERVERS,
        "sarvam": {
            "stt_model": settings.SARVAM_STT_MODEL,
            "llm_model": settings.SARVAM_CHAT_MODEL,
            "tts_model": settings.SARVAM_TTS_MODEL,
            "voice_id": settings.SARVAM_TTS_SPEAKER,
        },
    }


@router.post("/offer", name="live_voice_offer")
async def live_voice_offer(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    if not settings.SARVAM_API_KEY:
        raise HTTPException(status_code=503, detail="SARVAM_API_KEY is required for live voice.")

    SmallWebRTCRequest, _, _ = _pipecat_imports()
    payload = await request.json()
    language = _chat_language(str(request.query_params.get("language") or payload.get("language") or "en"))
    offer_request = SmallWebRTCRequest(**payload)

    async def webrtc_connection_callback(connection):
        background_tasks.add_task(run_live_bot, connection, language)

    return await _handler().handle_web_request(
        request=offer_request,
        webrtc_connection_callback=webrtc_connection_callback,
    )


@router.patch("/offer")
async def live_voice_ice_candidate(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    _, SmallWebRTCPatchRequest, _ = _pipecat_imports()
    patch_request = SmallWebRTCPatchRequest(**await request.json())
    await _handler().handle_patch_request(patch_request)
    return {"status": "success"}
