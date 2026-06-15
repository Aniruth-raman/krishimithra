"""
WhatsApp webhook router for KrishiMitra.

Production enhancements applied:
  1. Removed incomplete WhatsAppService / IntentRouter stubs.
  2. Replaced print() with structured logging throughout.
  3. DB rollback protection on every commit().
  4. Retry loop (3 attempts) in _download_twilio_media for transient timeouts.
  5. bulk_save_objects in _store_conversation for atomic conversation saves.
  6. LANGUAGE_ALIASES dict replaces brittle substring checks.
  7. os.makedirs(exist_ok=True) before writing crop images.
  8. Dedicated try/except around analyze_crop_image and chat_with_ai.
"""

import logging
import os
import re
import uuid
from dataclasses import dataclass
from html import escape
from typing import Optional
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_officer
from app.config import settings
from app.database import get_db
from app.models import AnalyticsEvent, Conversation, DiseaseReport, Grievance, User
from app.routers.chat import (
    detect_scheme_name,
    extract_tracking_id,
    format_grievance_tracking_result,
    format_scheme_result,
)
from app.routers.disease import ALLOWED_MIME_TYPES, validate_crop_image
from app.services.ai.sarvam_ai_service import (
    analyze_crop_image,
    chat_with_ai,
    check_scheme_eligibility,
    classify_grievance,
    classify_intent,
    get_weather_advisory,
)
from app.services.ai.sarvam_service import translate_text
from app.services.location_extractor import extract_location

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WhatsApp"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_LANGUAGES = {"en", "ta", "kn"}
LANGUAGE_AUDIO_CODES = {"en": "en-IN", "ta": "ta-IN", "kn": "kn-IN"}
LANGUAGE_NAMES = {"en": "English", "ta": "Tamil", "kn": "Kannada"}

# Fix 6 – structured alias table replaces brittle substring checks.
LANGUAGE_ALIASES: dict[str, set[str]] = {
    "en": {"1", "english", "en", "inglish"},
    "ta": {"2", "tamil", "ta", "தமிழ்", "tamizh"},
    "kn": {"3", "kannada", "kn", "ಕನ್ನಡ"},
}
LANGUAGE_MENU_TRIGGERS = {"language", "lang", "change language", "select language", "menu", "ಭಾಷೆ", "மொழி"}

LANGUAGE_PROMPTS = {
    "en": "Choose language:\n1. English\n2. Tamil\n3. Kannada\n\nReply with 1, 2, or 3.",
    "ta": "மொழியை தேர்வு செய்யவும்:\n1. English\n2. தமிழ்\n3. ಕನ್ನಡ\n\n1, 2 அல்லது 3 என்று பதில் அனுப்பவும்.",
    "kn": "ಭಾಷೆ ಆಯ್ಕೆ ಮಾಡಿ:\n1. English\n2. தமிழ்\n3. ಕನ್ನಡ\n\n1, 2 ಅಥವಾ 3 ಎಂದು ಉತ್ತರಿಸಿ.",
}

LANGUAGE_CONFIRMATIONS = {
    "en": "Language set to English. You can ask about crops, weather, schemes, grievances, or send a crop photo.",
    "ta": "மொழி தமிழாக அமைக்கப்பட்டது. பயிர், வானிலை, திட்டங்கள், புகார்கள் பற்றி கேட்கலாம் அல்லது பயிர் படத்தை அனுப்பலாம்.",
    "kn": "ಭಾಷೆ ಕನ್ನಡಕ್ಕೆ ಬದಲಿಸಲಾಗಿದೆ. ಬೆಳೆ, ಹವಾಮಾನ, ಯೋಜನೆಗಳು, ದೂರುಗಳು ಬಗ್ಗೆ ಕೇಳಬಹುದು ಅಥವಾ ಬೆಳೆ ಫೋಟೋ ಕಳುಹಿಸಬಹುದು.",
}

IMAGE_LABELS = {
    "en": {
        "diagnosis": "Diagnosis",
        "pest": "Pest",
        "severity": "Severity",
        "confidence": "Confidence",
        "treatment": "Treatment",
        "prevention": "Prevention",
        "needs_confirmation": "Needs field confirmation",
    },
    "ta": {
        "diagnosis": "நோய் கண்டறிதல்",
        "pest": "பூச்சி",
        "severity": "தீவிரம்",
        "confidence": "நம்பிக்கை",
        "treatment": "சிகிச்சை",
        "prevention": "தடுப்பு",
        "needs_confirmation": "வயலில் உறுதிப்படுத்த வேண்டும்",
    },
    "kn": {
        "diagnosis": "ರೋಗ ಗುರುತಿಸುವಿಕೆ",
        "pest": "ಕೀಟ",
        "severity": "ತೀವ್ರತೆ",
        "confidence": "ವಿಶ್ವಾಸ",
        "treatment": "ಚಿಕಿತ್ಸೆ",
        "prevention": "ತಡೆಗಟ್ಟುವಿಕೆ",
        "needs_confirmation": "ಕ್ಷೇತ್ರದಲ್ಲಿ ದೃಢೀಕರಣ ಬೇಕು",
    },
}

# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class WhatsAppSendRequest(BaseModel):
    to_number: str
    message: str


@dataclass
class IncomingImage:
    filename: str
    content_type: str


# ---------------------------------------------------------------------------
# TwiML helpers
# ---------------------------------------------------------------------------


def _twiml_message(text: str) -> Response:
    return Response(
        content=f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(text)}</Message></Response>',
        media_type="application/xml",
    )


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _normalise_phone(value: str) -> str:
    phone = (value or "").replace("whatsapp:", "").strip()
    return phone or "unknown-whatsapp-user"


def _short(text: str, limit: int = 1500) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    return cleaned[:limit] if len(cleaned) > limit else cleaned


def _preferred_language(user: User) -> str:
    language = (user.preferred_language or "en").split("-")[0].lower()
    return language if language in SUPPORTED_LANGUAGES else "en"


# Fix 6 – use LANGUAGE_ALIASES for precise matching with no false positives.
def _detect_language_command(message: str) -> str | None:
    value = re.sub(r"\s+", " ", (message or "").strip().lower())
    if value in LANGUAGE_MENU_TRIGGERS:
        return "menu"
    for lang_code, aliases in LANGUAGE_ALIASES.items():
        if value in aliases:
            return lang_code
    return None


# Fix 3 – DB rollback protection on language update.
def _set_language(db: Session, user: User, language: str) -> None:
    user.preferred_language = language
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(user)


async def _localize_text(text: str, language: str) -> str:
    if language == "en" or not text:
        return text
    try:
        return await translate_text(
            text,
            source_lang="en-IN",
            target_lang=LANGUAGE_AUDIO_CODES.get(language, "en-IN"),
        )
    except Exception as error:
        # Fix 2 – structured logging instead of print().
        logger.warning("WhatsApp translation failed: %s", error)
        return text


def _get_or_create_farmer(db: Session, whatsapp_from: str) -> User:
    phone = _normalise_phone(whatsapp_from)
    safe_phone = re.sub(r"\W+", "", phone) or uuid.uuid4().hex[:10]
    email = f"whatsapp-{safe_phone}@krishimitra.local"

    user = db.query(User).filter((User.phone == phone) | (User.email == email)).first()
    if user:
        if user.phone != phone:
            user.phone = phone
            # Fix 3 – rollback on failure.
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
            db.refresh(user)
        return user

    user = User(
        email=email,
        phone=phone,
        full_name=f"WhatsApp Farmer {phone}",
        hashed_password="whatsapp-user",
        role="farmer",
        preferred_language="en",
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        user = db.query(User).filter((User.phone == phone) | (User.email == email)).first()
        if not user:
            raise
    db.refresh(user)
    return user


def _farmer_context(user: User) -> dict:
    profile = user.farmer_profile
    if not profile:
        return {}
    return {
        "district": profile.district,
        "village": profile.village,
        "primary_crop": profile.primary_crop,
        "state": profile.state,
        "farmer_category": profile.farmer_category,
        "annual_income": profile.annual_income,
    }


# Fix 5 – atomic conversation save with bulk_save_objects.
def _store_conversation(
    db: Session,
    user: User,
    session_id: str,
    user_text: str,
    response_text: str,
    intent: str,
    language: str = "en",
) -> None:
    user_conv = Conversation(
        user_id=user.id,
        session_id=session_id,
        role="user",
        content=user_text,
        intent=intent,
        language=language,
    )
    assistant_conv = Conversation(
        user_id=user.id,
        session_id=session_id,
        role="assistant",
        content=response_text,
        intent=intent,
        language=language,
    )
    db.bulk_save_objects([user_conv, assistant_conv])
    # Fix 3 – rollback protection.
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


# ---------------------------------------------------------------------------
# Twilio media download
# ---------------------------------------------------------------------------


def _extension_from_media(url: str, content_type: str) -> str:
    parsed_extension = os.path.splitext(urlparse(url).path)[1].lower()
    if parsed_extension in {".jpg", ".jpeg", ".png", ".webp"}:
        return parsed_extension
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(content_type, ".jpg")


def _media_url_with_extension(url: str, extension: str) -> str:
    parsed = urlparse(url)
    path = parsed.path if parsed.path.endswith(extension) else f"{parsed.path}{extension}"
    return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, parsed.fragment))


# Fix 4 – retry loop for transient timeouts.
async def _download_twilio_media(url: str, expected_content_type: str = "") -> tuple[bytes, str, str]:
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="Twilio credentials are required to download WhatsApp media.",
        )

    extension = _extension_from_media(url, expected_content_type)
    candidate_urls = [url]
    if not os.path.splitext(urlparse(url).path)[1] and extension:
        candidate_urls.append(_media_url_with_extension(url, extension))

    last_status = None
    last_content_type = ""

    async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
        for candidate_url in candidate_urls:
            # Retry up to 3 times on timeout.
            for attempt in range(3):
                try:
                    response = await client.get(
                        candidate_url,
                        auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                        headers={"Accept": "image/*,*/*"},
                    )
                    break
                except httpx.TimeoutException:
                    if attempt == 2:
                        raise
                    logger.warning(
                        "Twilio media download timeout (attempt %d/3): %s",
                        attempt + 1,
                        candidate_url,
                    )

            last_status = response.status_code
            last_content_type = response.headers.get("content-type", "").split(";")[0].lower()

            if response.status_code in {401, 403}:
                # Fix 2 – structured log for auth failures.
                logger.warning("Twilio WhatsApp media auth failed with status %s.", response.status_code)
                raise HTTPException(
                    status_code=400,
                    detail="Could not download WhatsApp media. Twilio rejected the configured Account SID/Auth Token.",
                )
            if response.status_code >= 400:
                logger.warning(
                    "Twilio WhatsApp media download failed with status %s: %s",
                    response.status_code,
                    response.text[:300],
                )
                continue
            if last_content_type.startswith("image/"):
                return response.content, last_content_type, _extension_from_media(candidate_url, last_content_type)

            logger.warning(
                "Twilio WhatsApp media returned non-image content-type %s; trying extension fallback.",
                last_content_type,
            )

    raise HTTPException(
        status_code=400,
        detail=(
            f"Could not download WhatsApp media from Twilio. "
            f"Last status: {last_status}, content type: {last_content_type or 'unknown'}."
        ),
    )


# ---------------------------------------------------------------------------
# Media message handler
# ---------------------------------------------------------------------------


def _guess_crop_type(text: str) -> Optional[str]:
    lowered = (text or "").lower()
    crops = ["paddy", "rice", "tomato", "cotton", "banana", "chilli", "chili", "sugarcane", "maize", "groundnut"]
    return next((crop for crop in crops if crop in lowered), None)


async def _handle_media_message(
    *,
    db: Session,
    user: User,
    body: str,
    media_url: str,
    media_content_type: str,
    language: str,
) -> str:
    if media_content_type and media_content_type.lower() not in ALLOWED_MIME_TYPES:
        return await _localize_text("Please send a crop image in JPG, JPEG, PNG, or WebP format.", language)

    content, downloaded_content_type, extension = await _download_twilio_media(media_url, media_content_type)
    image = IncomingImage(filename=f"whatsapp{extension}", content_type=downloaded_content_type or media_content_type)
    metadata = validate_crop_image(image, content)

    filename = f"{uuid.uuid4()}{metadata['extension']}"

    # Fix 7 – create upload directory automatically if it doesn't exist.
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    image_path = os.path.join(settings.UPLOAD_DIR, filename)
    with open(image_path, "wb") as image_file:
        image_file.write(content)

    crop_type = _guess_crop_type(body)

    # Fix 8 – dedicated exception handling around AI crop analysis.
    try:
        analysis = await analyze_crop_image(image_path, crop_type, language=language)
    except Exception as exc:
        logger.exception("analyze_crop_image failed for %s: %s", image_path, exc)
        return await _localize_text(
            "Sorry, crop image analysis is currently unavailable. Please try again later.",
            language,
        )

    district = user.farmer_profile.district if user.farmer_profile else None

    report = DiseaseReport(
        user_id=user.id,
        crop_type=crop_type,
        image_path=image_path,
        disease_name=analysis.get("disease_name"),
        pest_name=analysis.get("pest_name"),
        severity=analysis.get("severity"),
        confidence_score=analysis.get("confidence_score"),
        description=analysis.get("description"),
        treatment=analysis.get("treatment"),
        district=district,
        analysis_json={"image": metadata, "analysis": analysis, "channel": "whatsapp"},
    )
    db.add(report)
    db.add(
        AnalyticsEvent(
            event_type="whatsapp_disease_report",
            user_id=user.id,
            data={
                "disease": analysis.get("disease_name"),
                "crop": crop_type,
                "severity": analysis.get("severity"),
            },
            district=district,
        )
    )
    # Fix 3 – rollback on disease report commit failure.
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return await _format_image_analysis(analysis, language)


async def _format_image_analysis(analysis: dict, language: str) -> str:
    labels = IMAGE_LABELS.get(language, IMAGE_LABELS["en"])
    report = _short(
        "\n".join(
            part
            for part in [
                f"{labels['diagnosis']}: {analysis.get('disease_name') or labels['needs_confirmation']}",
                f"{labels['pest']}: {analysis.get('pest_name')}" if analysis.get("pest_name") else "",
                f"{labels['severity']}: {analysis.get('severity') or 'unknown'}",
                f"{labels['confidence']}: {round(float(analysis.get('confidence_score') or 0) * 100)}%",
                analysis.get("description") or "",
                f"{labels['treatment']}: {analysis.get('treatment') or ''}",
                f"{labels['prevention']}: {analysis.get('preventive_measures') or ''}",
            ]
            if part
        )
    )
    if language != "en" and analysis.get("analysis_source") == "crop_rule_fallback":
        return _short(await _localize_text(report, language))
    return report


# ---------------------------------------------------------------------------
# Text message handler
# ---------------------------------------------------------------------------


def _looks_like_grievance_request(message: str) -> bool:
    lowered = message.lower()
    return any(
        word in lowered
        for word in ["complaint", "grievance", "register", "file", "delayed", "not received", "subsidy"]
    )


async def _create_whatsapp_grievance(db: Session, user: User, message: str, language: str) -> str:
    category = await classify_grievance(message)
    tracking_id = f"KM-2026-{uuid.uuid4().hex[:5].upper()}"
    grievance = Grievance(
        tracking_id=tracking_id,
        farmer_id=user.id,
        category=category,
        title=_short(message, 90) or "WhatsApp grievance",
        description=message,
        status="submitted",
        district=user.farmer_profile.district if user.farmer_profile else None,
        expected_resolution_days=30,
    )
    db.add(grievance)
    db.add(
        AnalyticsEvent(
            event_type="whatsapp_grievance_created",
            user_id=user.id,
            data={"tracking_id": tracking_id, "category": category},
            district=grievance.district,
        )
    )
    # Fix 3 – rollback on grievance commit failure.
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return await _localize_text(
        f"Grievance registered.\nTracking ID: {tracking_id}\nStatus: submitted\nExpected resolution: 30 days",
        language,
    )


async def _handle_text_message(db: Session, user: User, body: str, session_id: str) -> tuple[str, str, str]:
    message = (body or "").strip()
    language = _preferred_language(user)

    language_command = _detect_language_command(message)
    if language_command == "menu":
        return "language_menu", LANGUAGE_PROMPTS.get(language, LANGUAGE_PROMPTS["en"]), language
    if language_command in SUPPORTED_LANGUAGES:
        _set_language(db, user, language_command)
        return "language_set", LANGUAGE_CONFIRMATIONS[language_command], language_command

    if not message:
        return (
            "general",
            await _localize_text(
                "Hi, I am KrishiMitra. Ask me about crops, weather, schemes, grievances, or send a crop photo. "
                "Send 'language' to change language.",
                language,
            ),
            language,
        )

    context = _farmer_context(user)

    tracking_id = extract_tracking_id(message)
    if tracking_id:
        grievance = db.query(Grievance).filter(Grievance.tracking_id.ilike(tracking_id)).first()
        return (
            "grievance_track",
            await _localize_text(format_grievance_tracking_result(grievance, tracking_id), language),
            language,
        )

    intent = await classify_intent(message, fast=True)

    if intent == "weather":
        location = (
            extract_location(message)
            or context.get("district")
            or context.get("village")
            or context.get("state")
        )
        if not location:
            return (
                intent,
                await _localize_text(
                    "Please send your district or city for weather advice. Example: Can I spray today in Chennai?",
                    language,
                ),
                language,
            )
        return intent, await get_weather_advisory(
            crop_type=context.get("primary_crop") or "crop",
            district=location,
            query=message,
            language=language,
        ), language

    if intent == "scheme":
        result = await check_scheme_eligibility(
            scheme_name=detect_scheme_name(message),
            state=context.get("state"),
            land_ownership="unknown",
            farmer_category=context.get("farmer_category"),
            annual_income=context.get("annual_income"),
            language=language,
        )
        return intent, format_scheme_result(result, language), language

    if intent == "grievance" and _looks_like_grievance_request(message):
        return intent, await _create_whatsapp_grievance(db, user, message, language), language

    history_records = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id, Conversation.session_id == session_id)
        .order_by(Conversation.created_at.asc())
        .limit(12)
        .all()
    )
    history = [{"role": record.role, "content": record.content} for record in history_records]

    # Fix 8 – dedicated exception handling around chat_with_ai.
    try:
        response = await chat_with_ai(
            message=message,
            history=history,
            language=language,
            context=context or None,
        )
    except Exception as exc:
        logger.exception("chat_with_ai failed: %s", exc)
        response = await _localize_text(
            "Sorry, the AI assistant is temporarily unavailable. Please try again shortly.",
            language,
        )

    return intent, response, language


# ---------------------------------------------------------------------------
# Webhook endpoints
# ---------------------------------------------------------------------------


@router.api_route("/whatsapp/webhook", methods=["GET", "POST"])
@router.api_route("/whatsapp/twilio", methods=["GET", "POST"])
@router.api_route("/twilio/whatsapp", methods=["GET", "POST"])
async def whatsapp_webhook(
    From: str = Form(""),
    Body: Optional[str] = Form(None),
    NumMedia: int = Form(0),
    MediaUrl0: Optional[str] = Form(None),
    MediaContentType0: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    user = _get_or_create_farmer(db, From)
    session_id = f"whatsapp-{_normalise_phone(From)}"
    body = Body or ""
    language = _preferred_language(user)

    try:
        if NumMedia > 0 and MediaUrl0:
            response_text = await _handle_media_message(
                db=db,
                user=user,
                body=body,
                media_url=MediaUrl0,
                media_content_type=MediaContentType0 or "",
                language=language,
            )
            intent = "disease_image"
        else:
            intent, response_text, language = await _handle_text_message(db, user, body, session_id)

        _store_conversation(db, user, session_id, body or "[media]", response_text, intent, language)

    except HTTPException as error:
        response_text = await _localize_text(str(error.detail), language)

    except Exception as error:
        # Fix 2 – structured exception logging.
        logger.exception("WhatsApp webhook failed: %s", error)
        response_text = await _localize_text(
            "Sorry, KrishiMitra could not process this WhatsApp message. Please try again.",
            language,
        )

    return _twiml_message(_short(response_text))


@router.post("/whatsapp/send")
async def send_whatsapp_message(
    payload: WhatsAppSendRequest,
    current_user: User = Depends(get_officer),
):
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        raise HTTPException(status_code=400, detail="Twilio credentials are not configured.")

    from_number = settings.TWILIO_WHATSAPP_FROM or settings.TWILIO_FROM_NUMBER
    if not from_number:
        raise HTTPException(
            status_code=400,
            detail="Set TWILIO_WHATSAPP_FROM or TWILIO_FROM_NUMBER in backend/app/.env.",
        )

    from_value = from_number if from_number.startswith("whatsapp:") else f"whatsapp:{from_number}"
    to_value = (
        payload.to_number if payload.to_number.startswith("whatsapp:") else f"whatsapp:{payload.to_number}"
    )

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
            data={"From": from_value, "To": to_value, "Body": payload.message},
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Twilio WhatsApp send failed: {response.text}")

    data = response.json()
    return {"message": "WhatsApp message queued", "sid": data.get("sid"), "status": data.get("status")}