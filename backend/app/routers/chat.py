import re
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Conversation, Grievance, User
from app.schemas import ChatRequest, ChatResponse
from app.services.ai.sarvam_ai_service import (
    chat_with_ai,
    check_scheme_eligibility,
    classify_intent,
    get_weather_advisory,
)

router = APIRouter(prefix="/chat", tags=["Chat"])

SUPPORTED_SCHEMES = [
    "PM-KISAN",
    "Krushak Yojana",
    "Raitha Sakthi Yojana",
    "Mukhyamantri Samathuvapuram",
    "PM Fasal Bima Yojana",
    "Kisan Credit Card",
    "National Agriculture Market (eNAM)",
    "Pradhan Mantri Krishi Sinchayee Yojana",
    "Soil Health Card Scheme",
]


def extract_tracking_id(message: str) -> str | None:
    match = re.search(r"\b(GRV\d{8,}|KM-\d{4}-\d{4,})\b", message or "", re.IGNORECASE)
    return match.group(1).upper() if match else None


def format_grievance_tracking_result(grievance: Grievance | None, tracking_id: str) -> str:
    if not grievance:
        return (
            f"I could not find grievance {tracking_id} in this system.\n\n"
            "Please check the tracking ID once. If this grievance was created here, it should match exactly. "
            "If it was created from IVR, it may use the KM-2026 format."
        )

    updates = sorted(grievance.updates or [], key=lambda item: item.created_at, reverse=True)
    latest_update = updates[0] if updates else None
    parts = [
        f"Tracking ID: {grievance.tracking_id}",
        f"Status: {grievance.status}",
        f"Title: {grievance.title}",
        f"Category: {grievance.category}",
        f"District: {grievance.district or 'Not provided'}",
        f"Expected resolution: {grievance.expected_resolution_days} days",
    ]
    if grievance.resolution_notes:
        parts.append(f"Resolution notes: {grievance.resolution_notes}")
    elif latest_update and latest_update.notes:
        parts.append(f"Latest update: {latest_update.notes}")
    else:
        parts.append("Latest update: No officer notes yet.")
    return "\n".join(parts)


def detect_scheme_name(message: str) -> str:
    lowered = message.lower()
    aliases = {
        "PM-KISAN": ["pm-kisan", "pm kisan", "kisan samman", "samman nidhi"],
        "Mukhyamantri Samathuvapuram": ["samathuvapuram", "samathuva puram", "mukhyamantri samathuvapuram"],
        "Raitha Sakthi Yojana": ["raitha sakthi", "raita sakthi", "raitha shakti", "raita shakti"],
        "PM Fasal Bima Yojana": ["fasal bima", "pmfby", "crop insurance", "insurance"],
        "Kisan Credit Card": ["kisan credit", "kcc", "credit card", "crop loan"],
        "Soil Health Card Scheme": ["soil health", "soil card"],
        "National Agriculture Market (eNAM)": ["enam", "e-nam", "national agriculture market", "market"],
        "Pradhan Mantri Krishi Sinchayee Yojana": ["sinchayee", "pmksy", "irrigation"],
        "Krushak Yojana": ["krushak", "kalia"],
    }
    for scheme, words in aliases.items():
        if any(word in lowered for word in words):
            return scheme
    return "PM-KISAN"


SCHEME_LABELS = {
    "en": {
        "eligible": "Eligible",
        "not_eligible": "Not eligible",
        "requires_verification": "Needs verification",
        "assessment": "Eligibility assessment",
        "reason": "Reason",
        "benefits": "Benefits",
        "documents": "Documents required",
        "next_step": "Next official step",
        "alternatives": "Alternative schemes",
        "verify": "Verification notes",
    },
    "ta": {
        "eligible": "தகுதி உள்ளது",
        "not_eligible": "தகுதி இல்லை",
        "requires_verification": "சரிபார்ப்பு தேவை",
        "assessment": "தகுதி மதிப்பீடு",
        "reason": "காரணம்",
        "benefits": "நன்மைகள்",
        "documents": "தேவையான ஆவணங்கள்",
        "next_step": "அடுத்த அதிகாரப்பூர்வ படி",
        "alternatives": "மாற்று திட்டங்கள்",
        "verify": "சரிபார்க்க வேண்டியது",
    },
    "hi": {
        "eligible": "योग्य",
        "not_eligible": "योग्य नहीं",
        "requires_verification": "सत्यापन आवश्यक",
        "assessment": "पात्रता आकलन",
        "reason": "कारण",
        "benefits": "लाभ",
        "documents": "आवश्यक दस्तावेज",
        "next_step": "अगला आधिकारिक कदम",
        "alternatives": "वैकल्पिक योजनाएं",
        "verify": "सत्यापन नोट्स",
    },
    "kn": {
        "eligible": "ಅರ್ಹ",
        "not_eligible": "ಅರ್ಹರಲ್ಲ",
        "requires_verification": "ಪರಿಶೀಲನೆ ಅಗತ್ಯ",
        "assessment": "ಅರ್ಹತಾ ಮೌಲ್ಯಮಾಪನ",
        "reason": "ಕಾರಣ",
        "benefits": "ಪ್ರಯೋಜನಗಳು",
        "documents": "ಅಗತ್ಯ ದಾಖಲೆಗಳು",
        "next_step": "ಮುಂದಿನ ಅಧಿಕೃತ ಹಂತ",
        "alternatives": "ಪರ್ಯಾಯ ಯೋಜನೆಗಳು",
        "verify": "ಪರಿಶೀಲನೆ ಸೂಚನೆಗಳು",
    },
}


def _scheme_labels(language: str) -> dict:
    return SCHEME_LABELS.get((language or "en").split("-")[0], SCHEME_LABELS["en"])


def format_scheme_result(result: dict, language: str = "en") -> str:
    base_language = (language or "en").split("-")[0]
    labels = _scheme_labels(language)
    status = result.get("eligibility_status")
    if status == "eligible":
        heading = labels["eligible"]
    elif status == "not_eligible":
        heading = labels["not_eligible"]
    else:
        heading = labels["requires_verification"]
    documents = ", ".join(result.get("required_documents") or [])
    alternatives = ", ".join(result.get("alternative_schemes") or [])
    if base_language == "en":
        parts = [
            f"Eligibility for {result.get('scheme_name')}: {heading}.",
            result.get("eligibility_reason", ""),
            f"You may get: {result.get('benefits', '-')}",
            f"Keep these documents ready: {documents or '-'}",
            f"Next, {result.get('application_steps', '-')}",
        ]
        if result.get("verification_notes"):
            parts.append(f"Also verify: {result.get('verification_notes')}")
        if alternatives:
            parts.append(f"If this does not work, check: {alternatives}")
    else:
        parts = [
            f"{labels['assessment']}: {heading} - {result.get('scheme_name')}",
            f"{labels['reason']}: {result.get('eligibility_reason', '-')}",
            f"{labels['benefits']}: {result.get('benefits', '-')}",
            f"{labels['documents']}: {documents or '-'}",
            f"{labels['next_step']}: {result.get('application_steps', '-')}",
        ]
        if result.get("verification_notes"):
            parts.append(f"{labels['verify']}: {result.get('verification_notes')}")
        if alternatives:
            parts.append(f"{labels['alternatives']}: {alternatives}")
    return "\n\n".join(part for part in parts if part)


def _farmer_context(current_user: User) -> dict:
    farmer_profile = current_user.farmer_profile
    if not farmer_profile:
        return {}
    return {
        "district": farmer_profile.district,
        "primary_crop": farmer_profile.primary_crop,
        "land_size": farmer_profile.land_size_acres,
        "state": farmer_profile.state,
        "farmer_category": farmer_profile.farmer_category,
        "annual_income": farmer_profile.annual_income,
    }


async def _store_conversation(
    db: Session,
    current_user: User,
    session_id: str,
    request: ChatRequest,
    intent: str,
    response_text: str,
) -> None:
    db.add(Conversation(
        user_id=current_user.id,
        session_id=session_id,
        role="user",
        content=request.message,
        intent=intent,
        language=request.language,
    ))
    db.add(Conversation(
        user_id=current_user.id,
        session_id=session_id,
        role="assistant",
        content=response_text,
        intent=intent,
        language=request.language,
    ))
    db.commit()


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_id = request.session_id or str(uuid.uuid4())
    history_records = (
        db.query(Conversation)
        .filter(
            Conversation.user_id == current_user.id,
            Conversation.session_id == session_id,
        )
        .order_by(Conversation.created_at.asc())
        .limit(20)
        .all()
    )
    history = [{"role": record.role, "content": record.content} for record in history_records]

    tracking_id = extract_tracking_id(request.message)
    if tracking_id:
        grievance = db.query(Grievance).filter(Grievance.tracking_id.ilike(tracking_id)).first()
        intent = "grievance_track"
        response_text = format_grievance_tracking_result(grievance, tracking_id)
        await _store_conversation(db, current_user, session_id, request, intent, response_text)
        return ChatResponse(response=response_text, intent=intent, session_id=session_id)

    intent = await classify_intent(request.message)
    context = _farmer_context(current_user)

    if intent == "weather" and context.get("district"):
        response_text = await get_weather_advisory(
            crop_type=context.get("primary_crop", "crop"),
            district=context.get("district", "your district"),
            query=request.message,
            language=request.language,
        )
    elif intent == "scheme":
        scheme_result = await check_scheme_eligibility(
            scheme_name=detect_scheme_name(request.message),
            state=context.get("state"),
            land_ownership="unknown",
            farmer_category=context.get("farmer_category"),
            annual_income=context.get("annual_income"),
            language=request.language,
        )
        response_text = format_scheme_result(scheme_result, request.language)
    else:
        response_text = await chat_with_ai(
            message=request.message,
            history=history,
            language=request.language,
            context=context if context else None,
        )

    await _store_conversation(db, current_user, session_id, request, intent, response_text)
    return ChatResponse(response=response_text, intent=intent, session_id=session_id)


@router.get("/history")
async def get_chat_history(
    session_id: str = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Conversation).filter(Conversation.user_id == current_user.id)
    if session_id:
        query = query.filter(Conversation.session_id == session_id)
    messages = query.order_by(Conversation.created_at.desc()).limit(limit).all()
    return [
        {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "intent": message.intent,
            "session_id": message.session_id,
            "created_at": message.created_at,
        }
        for message in reversed(messages)
    ]


@router.get("/sessions")
async def get_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from sqlalchemy import func

    sessions = (
        db.query(
            Conversation.session_id,
            func.min(Conversation.created_at).label("started_at"),
            func.count(Conversation.id).label("message_count"),
        )
        .filter(Conversation.user_id == current_user.id)
        .group_by(Conversation.session_id)
        .order_by(func.min(Conversation.created_at).desc())
        .limit(20)
        .all()
    )
    return [{"session_id": session.session_id, "started_at": session.started_at, "message_count": session.message_count} for session in sessions]
