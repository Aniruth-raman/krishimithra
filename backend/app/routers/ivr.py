import random
import re
import uuid
from datetime import datetime
from html import escape
from typing import Any, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_officer
from app.config import settings
from app.database import get_db
from app.models import AnalyticsEvent, Grievance, IvrSession, User
from app.services.ai.sarvam_ai_service import chat_with_ai, classify_grievance
from app.services.ivr.providers.twilio_provider import TwilioProvider
from app.services.location_extractor import extract_location
from app.services.weather_service import WeatherLookupError, fetch_weather


router = APIRouter(prefix="/ivr", tags=["IVR"])
twilio_provider = TwilioProvider()


class IncomingCall(BaseModel):
    phone_number: str
    provider: str = "mock"


class OutboundCall(BaseModel):
    to_number: str


class DemoScenarioCall(BaseModel):
    to_number: str
    scenario: str = "crop"


MENU_OPTIONS = {
    "1": "crop",
    "2": "weather",
    "3": "scheme",
    "4": "grievance",
    "5": "track",
}

SCENARIO_MESSAGES = {
    "crop": (
        "Crop help selected. Check affected leaves closely, compare nearby plants, "
        "avoid blind pesticide mixing, and upload a clear image in the app for diagnosis."
    ),
    "weather": (
        "Weather help selected. If rain is likely or wind is high, delay pesticide spraying. "
        "Spray only in low wind and follow the product label."
    ),
    "scheme": (
        "Scheme help selected. Keep Aadhaar, bank passbook, land record, mobile number, "
        "and e K Y C details ready. Eligibility depends on official scheme rules."
    ),
    "grievance": (
        "Grievance help selected. Keep application number, Aadhaar, bank details, land record, "
        "photos, and office visit dates ready before filing."
    ),
    "track": "Tracking help selected. Enter or say the last five digits of your grievance tracking number.",
}

SCENARIO_ALIASES = {
    "disease": "crop",
    "pest": "crop",
    "complaint": "grievance",
    "status": "track",
    "tracking": "track",
}


def public_url(path: str) -> str:
    prefix = settings.PUBLIC_WEBHOOK_PREFIX.strip("/")
    full_path = f"/{prefix}{path}" if prefix else path
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}{full_path}"


def twiml_response(twiml: str) -> Response:
    return Response(content=twiml, media_type="application/xml")


def say(text: str) -> str:
    return f"<Say>{escape(text)}</Say>"


def redirect(path: str) -> str:
    return f'<Redirect method="POST">{escape(public_url(path))}</Redirect>'


def gather(*, action: str, prompt: str, input_type: str = "dtmf speech", num_digits: int = 1, timeout: int = 8) -> str:
    return (
        f'<Gather input="{escape(input_type)}" numDigits="{num_digits}" timeout="{timeout}" '
        f'speechTimeout="auto" language="en-IN" action="{escape(public_url(action))}" method="POST">'
        f"{say(prompt)}"
        "</Gather>"
    )


def response_xml(*parts: str) -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Response>' + "".join(parts) + "</Response>"


def session_action(session_id: str, path: str) -> str:
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}session_id={session_id}"


def _session_payload(session: IvrSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "phone_number": session.phone_number,
        "provider": session.provider,
        "language": session.language,
        "current_state": session.current_state,
        "context": session.context or {},
        "status": session.status,
        "last_intent": session.last_intent,
        "last_transcript": session.last_transcript,
        "updated_at": session.updated_at,
    }


def _get_or_create_session(db: Session, phone_number: str, provider: str = "twilio") -> IvrSession:
    phone = phone_number or "unknown-caller"
    session = (
        db.query(IvrSession)
        .filter(IvrSession.phone_number == phone, IvrSession.provider == provider, IvrSession.status == "active")
        .order_by(IvrSession.updated_at.desc())
        .first()
    )
    if session:
        return session

    session = IvrSession(
        session_id=str(uuid.uuid4()),
        phone_number=phone,
        provider=provider,
        language="en",
        current_state="WELCOME",
        context={},
        status="active",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    _log_event(db, "ivr_call_started", session, {"provider": provider})
    return session


def _get_session(db: Session, session_id: Optional[str], phone_number: Optional[str] = None) -> IvrSession:
    session = db.query(IvrSession).filter(IvrSession.session_id == session_id).first() if session_id else None
    if session:
        return session
    return _get_or_create_session(db, phone_number or "unknown-caller", "twilio")


def _update_session(
    db: Session,
    session: IvrSession,
    *,
    state: Optional[str] = None,
    intent: Optional[str] = None,
    transcript: Optional[str] = None,
    context: Optional[dict[str, Any]] = None,
    status: Optional[str] = None,
) -> None:
    if state is not None:
        session.current_state = state
    if intent is not None:
        session.last_intent = intent
    if transcript is not None:
        session.last_transcript = transcript
    if context is not None:
        session.context = context
    if status is not None:
        session.status = status
    session.updated_at = datetime.utcnow()
    db.commit()


def _log_event(db: Session, event_type: str, session: IvrSession, payload: dict[str, Any]) -> None:
    db.add(
        AnalyticsEvent(
            event_type=event_type,
            data={"session_id": session.session_id, "phone_number": session.phone_number, **payload},
        )
    )
    db.commit()


def _find_or_create_farmer(db: Session, phone_number: str) -> User:
    farmer = db.query(User).filter(User.phone == phone_number).first()
    if farmer:
        return farmer
    safe_phone = re.sub(r"\W+", "", phone_number or "unknown") or uuid.uuid4().hex[:10]
    farmer = User(
        email=f"ivr-{safe_phone}@krishimitra.local",
        phone=phone_number,
        full_name=f"IVR Farmer {phone_number}",
        hashed_password="ivr-user",
        role="farmer",
        preferred_language="en",
        is_active=True,
    )
    db.add(farmer)
    db.commit()
    db.refresh(farmer)
    return farmer


def _main_menu_twiml(session: IvrSession, intro: Optional[str] = None) -> str:
    prompt = (
        "Main menu. Press 1 for crop disease and pest help. "
        "Press 2 for weather and spray advice. "
        "Press 3 for government scheme guidance. "
        "Press 4 to register a grievance. "
        "Press 5 to track a grievance. "
        "Press 9 to repeat."
    )
    parts = [say(intro)] if intro else []
    parts.append(gather(action=session_action(session.session_id, "/ivr/twilio/menu"), prompt=prompt, num_digits=1))
    parts.append(say("I did not receive input. Returning to the main menu."))
    parts.append(redirect(session_action(session.session_id, "/ivr/twilio/welcome")))
    return response_xml(*parts)


def _detect_option(digits: Optional[str], speech: Optional[str]) -> Optional[str]:
    digit = (digits or "").strip()
    if digit in MENU_OPTIONS:
        return MENU_OPTIONS[digit]
    if digit == "9":
        return "repeat"

    spoken = (speech or "").strip().lower()
    if any(word in spoken for word in ["crop", "disease", "pest", "leaf", "plant"]):
        return "crop"
    if any(word in spoken for word in ["weather", "rain", "spray", "wind", "irrigation"]):
        return "weather"
    if any(word in spoken for word in ["scheme", "subsidy", "yojana", "kisan"]):
        return "scheme"
    if any(word in spoken for word in ["grievance", "complaint", "problem", "issue"]):
        return "grievance"
    if any(word in spoken for word in ["track", "tracking", "status"]):
        return "track"
    return None


def _normalise_scenario(value: str) -> str:
    scenario = (value or "").strip().lower()
    return SCENARIO_ALIASES.get(scenario, scenario)


def _prompt_for_option(session: IvrSession, option: str) -> str:
    prompts = {
        "crop": "After the beep, say your crop name and symptoms. For example, paddy leaves are yellow with brown spots.",
        "weather": "After the beep, say your district or city and what you want to do. For example, can I spray today in Chennai?",
        "scheme": "After the beep, say the scheme name or your need. For example, PM Kisan eligibility or crop insurance.",
        "grievance": "After the beep, describe your grievance clearly. Mention application number, district, amount, and date if you know them.",
        "track": "Enter or say the last five digits of your grievance tracking number.",
    }
    return response_xml(
        say(SCENARIO_MESSAGES.get(option, "")),
        gather(
            action=session_action(session.session_id, f"/ivr/twilio/{option}"),
            prompt=prompts[option],
            input_type="dtmf speech" if option == "track" else "speech dtmf",
            num_digits=5 if option == "track" else 1,
            timeout=10,
        ),
        say("I did not receive input. Returning to the main menu."),
        redirect(session_action(session.session_id, "/ivr/twilio/welcome")),
    )


def _finish_twiml(message: str, session: IvrSession, *, repeat: bool = True) -> str:
    if not repeat:
        return response_xml(say(message), say("Thank you for calling KrishiMitra."), "<Hangup/>")
    return response_xml(
        say(message),
        gather(
            action=session_action(session.session_id, "/ivr/twilio/menu"),
            prompt="Press 9 to return to the main menu, or press any other key to end the call.",
            input_type="dtmf",
            num_digits=1,
            timeout=6,
        ),
        say("Thank you for calling KrishiMitra."),
        "<Hangup/>",
    )


def _short(text: str, limit: int = 650) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    return cleaned[:limit] if len(cleaned) > limit else cleaned


async def _crop_response(text: str, session: IvrSession) -> str:
    if not text:
        return "I could not hear the crop symptoms. Please call again and say the crop name and visible symptoms."
    answer = await chat_with_ai(
        message=text,
        history=[],
        language="en",
        context={"channel": "ivr", "phone_number": session.phone_number},
        channel="ivr",
    )
    return _short(answer)


async def _weather_response(text: str) -> str:
    location = extract_location(text)
    if not location:
        return "I need your district or city for weather advice. Please call again and say something like, can I spray today in Chennai."
    try:
        weather = await fetch_weather(location)
        return _short(weather.get("farmer_report") or weather.get("forecast_3days") or f"Weather is available for {location}.")
    except WeatherLookupError:
        return f"I could not find weather for {location}. Please check the city or district name."
    except Exception:
        return "Weather service is temporarily unavailable. If rain is likely or wind is high, delay pesticide spraying."


def _scheme_response(text: str) -> str:
    lowered = (text or "").lower()
    if "insurance" in lowered or "fasal" in lowered or "bima" in lowered:
        return "For PM Fasal Bima Yojana, check notified crop, season, area, cut-off date, Aadhaar, bank passbook, and cultivation proof. Final eligibility depends on official state notification."
    if "credit" in lowered or "kcc" in lowered or "loan" in lowered:
        return "For Kisan Credit Card, keep identity proof, land or cultivation document, crop details, bank account, and photo ready. Bank approval depends on crop plan and credit appraisal."
    return "For PM Kisan or subsidy support, keep Aadhaar, bank account, mobile number, land record, and e K Y C ready. Final eligibility depends on landholding and official exclusion checks."


async def _create_grievance(db: Session, text: str, session: IvrSession) -> str:
    description = text.strip() if text else "IVR grievance without clear transcript."
    farmer = _find_or_create_farmer(db, session.phone_number)
    category = await classify_grievance(description)
    tracking_id = f"KM-2026-{random.randint(10000, 99999)}"
    grievance = Grievance(
        tracking_id=tracking_id,
        farmer_id=farmer.id,
        category=category,
        title=_short(description, 90) or "IVR grievance",
        description=description,
        status="submitted",
        expected_resolution_days=30,
    )
    db.add(grievance)
    db.commit()
    _log_event(db, "ivr_grievance_created", session, {"tracking_id": tracking_id, "category": category})
    return f"Your grievance has been registered. Tracking number is {tracking_id}. Please save this number."


def _track_grievance(db: Session, digits: str) -> str:
    clean = "".join(ch for ch in digits if ch.isalnum())
    if not clean:
        return "I did not receive a tracking number."
    grievance = (
        db.query(Grievance)
        .filter(Grievance.tracking_id.ilike(f"%{clean}"))
        .order_by(Grievance.created_at.desc())
        .first()
    )
    if not grievance:
        return "No grievance was found for that tracking number. Please check the number and try again."
    return f"Tracking number {grievance.tracking_id}. Current status is {grievance.status}. Expected resolution is {grievance.expected_resolution_days} days."


@router.api_route("/incoming", methods=["GET", "POST"])
async def incoming_call(request: Request, db: Session = Depends(get_db)):
    if request.method == "GET":
        phone_number = request.query_params.get("From") or request.query_params.get("phone_number") or "browser-test"
        provider = request.query_params.get("provider") or "twilio"
    else:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            body = await request.json()
            phone_number = body.get("phone_number") or body.get("From") or body.get("To") or "unknown-caller"
            provider = body.get("provider") or "mock"
        else:
            form = await request.form()
            phone_number = str(form.get("From") or form.get("To") or "unknown-caller")
            provider = str(form.get("provider") or "twilio")

    session = _get_or_create_session(db, phone_number, provider)
    _update_session(db, session, state="MAIN_MENU", intent=None)
    if provider == "twilio":
        return twiml_response(_main_menu_twiml(session, "Welcome to KrishiMitra farmer helpline."))
    return {
        "session": _session_payload(session),
        "prompt": "Welcome to KrishiMitra. Choose 1 crop, 2 weather, 3 scheme, 4 grievance, 5 track.",
        "options": MENU_OPTIONS,
    }


@router.post("/callback")
async def callback(
    session_id: Optional[str] = Form(None),
    phone_number: Optional[str] = Form(None),
    provider: str = Form("mock"),
    digits: Optional[str] = Form(None),
    text: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    session = _get_session(db, session_id, phone_number)
    option = _detect_option(digits, text)
    if not option or option == "repeat":
        return {"session": _session_payload(session), "prompt": "Main menu", "options": MENU_OPTIONS}
    _update_session(db, session, state=option.upper(), intent=option, transcript=text)
    return {"session": _session_payload(session), "selected": option, "message": SCENARIO_MESSAGES[option]}


@router.get("/session/{session_id}")
async def get_session(session_id: str, db: Session = Depends(get_db)):
    session = db.query(IvrSession).filter(IvrSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="IVR session not found")
    return _session_payload(session)


@router.get("/sessions")
async def get_recent_sessions(
    limit: int = 20,
    current_user: User = Depends(get_officer),
    db: Session = Depends(get_db),
):
    sessions = db.query(IvrSession).order_by(IvrSession.updated_at.desc()).limit(max(1, min(limit, 100))).all()
    return [_session_payload(session) for session in sessions]


@router.post("/twilio/call")
async def place_twilio_call(payload: OutboundCall, current_user: User = Depends(get_officer)):
    base_url = settings.PUBLIC_BASE_URL.rstrip("/")
    if base_url.startswith("http://127.0.0.1") or base_url.startswith("http://localhost"):
        raise HTTPException(status_code=400, detail="Set PUBLIC_BASE_URL to your public ngrok URL before placing Twilio calls.")
    try:
        result = await twilio_provider.place_call(payload.to_number, public_url("/ivr/twilio/welcome"))
        return {"message": "IVR call initiated", "call_sid": result.get("sid"), "status": result.get("status")}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/twilio/test-call")
async def place_twilio_test_call(payload: OutboundCall, current_user: User = Depends(get_officer)):
    twiml = response_xml(say("KrishiMitra IVR test call is working."))
    try:
        result = await twilio_provider.place_twiml_call(payload.to_number, twiml)
        return {"message": "Test call initiated", "call_sid": result.get("sid"), "status": result.get("status")}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/twilio/demo-call")
async def place_twilio_demo_call(payload: OutboundCall, current_user: User = Depends(get_officer)):
    twiml = response_xml(
        gather(
            action="/ivr/twilio/demo/menu",
            prompt=(
                "Welcome to KrishiMitra phone tree demo. Press 1 crop help. "
                "Press 2 weather. Press 3 scheme. Press 4 grievance. Press 5 tracking."
            ),
            num_digits=1,
        ),
        say("No input received. Thank you for calling KrishiMitra."),
    )
    try:
        result = await twilio_provider.place_twiml_call(payload.to_number, twiml)
        return {"message": "Demo call initiated", "call_sid": result.get("sid"), "status": result.get("status")}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/twilio/demo-scenario-call")
async def place_twilio_demo_scenario_call(payload: DemoScenarioCall, current_user: User = Depends(get_officer)):
    scenario = _normalise_scenario(payload.scenario)
    message = SCENARIO_MESSAGES.get(scenario)
    if not message:
        raise HTTPException(status_code=400, detail="Invalid scenario. Use crop, weather, scheme, grievance, or track.")
    twiml = response_xml(say(message), say("This scenario demo is complete. Thank you for calling KrishiMitra."))
    try:
        result = await twilio_provider.place_twiml_call(payload.to_number, twiml)
        return {"message": f"{scenario.title()} demo call initiated", "call_sid": result.get("sid"), "status": result.get("status"), "scenario": scenario}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.api_route("/twilio/ping", methods=["GET", "POST"])
async def twilio_ping():
    return twiml_response(response_xml(say("KrishiMitra IVR webhook reached successfully.")))


@router.api_route("/twilio/welcome", methods=["GET", "POST"])
@router.api_route("/twilio/incoming", methods=["GET", "POST"])
async def twilio_welcome(
    From: Optional[str] = Form(None),
    To: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    session = _get_or_create_session(db, From or To or "unknown-twilio-caller", "twilio")
    _update_session(db, session, state="MAIN_MENU", intent=None)
    return twiml_response(_main_menu_twiml(session, "Welcome to KrishiMitra farmer helpline."))


@router.api_route("/twilio/demo", methods=["GET", "POST"])
@router.api_route("/twilio/interactive-demo", methods=["GET", "POST"])
async def twilio_demo():
    return twiml_response(
        response_xml(
            gather(
                action="/ivr/twilio/demo/menu",
                prompt=(
                    "Welcome to KrishiMitra phone tree demo. Press 1 crop help. "
                    "Press 2 weather. Press 3 scheme. Press 4 grievance. Press 5 tracking."
                ),
                num_digits=1,
            ),
            say("No input received. Thank you for calling KrishiMitra."),
        )
    )


@router.api_route("/twilio/demo/menu", methods=["GET", "POST"])
async def twilio_demo_menu(Digits: Optional[str] = Form(None), SpeechResult: Optional[str] = Form(None)):
    option = _detect_option(Digits, SpeechResult)
    if not option or option == "repeat":
        return await twilio_demo()
    return twiml_response(response_xml(say(SCENARIO_MESSAGES[option]), redirect("/ivr/twilio/demo")))


@router.api_route("/twilio/menu", methods=["GET", "POST"])
async def twilio_menu(
    session_id: Optional[str] = None,
    From: Optional[str] = Form(None),
    Digits: Optional[str] = Form(None),
    SpeechResult: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    session = _get_session(db, session_id, From)
    option = _detect_option(Digits, SpeechResult)
    if not option or option == "repeat":
        return twiml_response(_main_menu_twiml(session, "Returning to the main menu."))
    _update_session(db, session, state=option.upper(), intent=option, transcript=SpeechResult)
    return twiml_response(_prompt_for_option(session, option))


@router.api_route("/twilio/crop", methods=["GET", "POST"])
async def twilio_crop(
    session_id: Optional[str] = None,
    From: Optional[str] = Form(None),
    SpeechResult: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    session = _get_session(db, session_id, From)
    answer = await _crop_response(SpeechResult or "", session)
    _update_session(db, session, state="MAIN_MENU", intent="crop", transcript=SpeechResult)
    _log_event(db, "ivr_crop_query", session, {"transcript": SpeechResult or ""})
    return twiml_response(_finish_twiml(answer, session))


@router.api_route("/twilio/weather", methods=["GET", "POST"])
async def twilio_weather(
    session_id: Optional[str] = None,
    From: Optional[str] = Form(None),
    SpeechResult: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    session = _get_session(db, session_id, From)
    answer = await _weather_response(SpeechResult or "")
    _update_session(db, session, state="MAIN_MENU", intent="weather", transcript=SpeechResult)
    _log_event(db, "ivr_weather_query", session, {"transcript": SpeechResult or ""})
    return twiml_response(_finish_twiml(answer, session))


@router.api_route("/twilio/scheme", methods=["GET", "POST"])
async def twilio_scheme(
    session_id: Optional[str] = None,
    From: Optional[str] = Form(None),
    SpeechResult: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    session = _get_session(db, session_id, From)
    answer = _scheme_response(SpeechResult or "")
    _update_session(db, session, state="MAIN_MENU", intent="scheme", transcript=SpeechResult)
    _log_event(db, "ivr_scheme_query", session, {"transcript": SpeechResult or ""})
    return twiml_response(_finish_twiml(answer, session))


@router.api_route("/twilio/grievance", methods=["GET", "POST"])
async def twilio_grievance(
    session_id: Optional[str] = None,
    From: Optional[str] = Form(None),
    SpeechResult: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    session = _get_session(db, session_id, From)
    answer = await _create_grievance(db, SpeechResult or "", session)
    _update_session(db, session, state="MAIN_MENU", intent="grievance", transcript=SpeechResult)
    return twiml_response(_finish_twiml(answer, session))


@router.api_route("/twilio/track", methods=["GET", "POST"])
async def twilio_track(
    session_id: Optional[str] = None,
    From: Optional[str] = Form(None),
    Digits: Optional[str] = Form(None),
    SpeechResult: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    session = _get_session(db, session_id, From)
    answer = _track_grievance(db, Digits or SpeechResult or "")
    _update_session(db, session, state="MAIN_MENU", intent="track", transcript=Digits or SpeechResult)
    _log_event(db, "ivr_track_query", session, {"input": Digits or SpeechResult or ""})
    return twiml_response(_finish_twiml(answer, session))
