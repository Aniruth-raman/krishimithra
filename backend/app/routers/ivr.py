from html import escape
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_officer
from app.config import settings
from app.database import get_db
from app.models import User
from app.services.ai.sarvam_service import transcribe_audio
from app.services.ivr.ivr_service import IvrService


router = APIRouter(prefix="/ivr", tags=["IVR"])
ivr_service = IvrService()


def public_url(path: str) -> str:
    prefix = settings.PUBLIC_WEBHOOK_PREFIX.strip("/")
    full_path = f"/{prefix}{path}" if prefix else path
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}{full_path}"


def public_asset_base_url() -> str:
    prefix = settings.PUBLIC_WEBHOOK_PREFIX.strip("/")
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/{prefix}".rstrip("/") if prefix else settings.PUBLIC_BASE_URL.rstrip("/")


def twiml_response(twiml: str) -> Response:
    return Response(content=twiml, media_type="application/xml")


def say(text: str) -> str:
    return f"<Say>{escape(text)}</Say>"


def interactive_demo_menu_twiml(intro: str | None = None) -> str:
    prompt = (
        "Press 1 or say disease for crop disease help. "
        "Press 2 or say grievance to register a grievance. "
        "Press 3 or say scheme for scheme eligibility. "
        "Press 4 or say weather for weather advice."
    )
    action_url = public_url("/ivr/twilio/interactive-demo/handle")
    intro_xml = say(intro) if intro else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"{intro_xml}"
        f'<Gather input="dtmf speech" numDigits="1" timeout="10" speechTimeout="auto" language="en-IN" action="{escape(action_url)}" method="POST">'
        f"{say(prompt)}"
        "</Gather>"
        f"{say('I did not receive input. Let us try once more.')}"
        f'<Redirect method="POST">{escape(public_url("/ivr/twilio/interactive-demo"))}</Redirect>'
        "</Response>"
    )


def detect_demo_choice(digits: str | None, speech: str | None) -> str | None:
    digit = (digits or "").strip()
    spoken = (speech or "").strip().lower()
    if digit == "1" or any(word in spoken for word in ["disease", "crop", "pest", "leaf", "plant"]):
        return "disease"
    if digit == "2" or any(word in spoken for word in ["grievance", "complaint", "subsidy", "issue"]):
        return "grievance"
    if digit == "3" or any(word in spoken for word in ["scheme", "eligibility", "kisan", "yojana"]):
        return "scheme"
    if digit == "4" or any(word in spoken for word in ["weather", "rain", "spray", "irrigation"]):
        return "weather"
    return None


class IncomingCall(BaseModel):
    phone_number: str
    provider: str = "mock"


class OutboundCall(BaseModel):
    to_number: str


class DemoScenarioCall(BaseModel):
    to_number: str
    scenario: str = "disease"


DEMO_SCENARIOS = {
    "disease": (
        "KrishiMitra disease demo. The farmer says tomato leaves have yellow spots and curling. "
        "Advice: inspect nearby plants, remove badly affected leaves, avoid overhead irrigation, and contact the local agriculture officer if it spreads quickly."
    ),
    "grievance": (
        "KrishiMitra grievance demo. The farmer reports delayed crop loss subsidy. "
        "A grievance is prepared with Aadhaar, bank details, land record, and application number. Demo tracking number is G R V 2 0 2 6 7 9 4 4 9."
    ),
    "scheme": (
        "KrishiMitra scheme demo. For PM Kisan, land ownership, Aadhaar, bank account, mobile number, and e K Y C are checked. "
        "Final eligibility depends on official exclusion checks."
    ),
    "weather": (
        "KrishiMitra weather demo. If rain is expected, delay pesticide spraying. Spray only in low wind, wear protection, and verify the product label."
    ),
}


def demo_twiml(message: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Say>{message}</Say>"
        "<Pause length=\"1\"/>"
        "<Say>This callback-free phone demo is complete. Thank you for calling KrishiMitra.</Say>"
        "</Response>"
    )


@router.api_route("/incoming", methods=["GET", "POST"])
async def incoming_call(request: Request, db: Session = Depends(get_db)):
    payload = await _read_incoming_payload(request)
    provider = payload.provider.lower()
    if provider == "twilio":
        return await _twilio_incoming_response(payload.phone_number, None, db)
    return await ivr_service.incoming_call(db, payload.phone_number, payload.provider)


@router.post("/callback")
async def callback(
    session_id: Optional[str] = Form(None),
    phone_number: Optional[str] = Form(None),
    provider: str = Form("mock"),
    digits: Optional[str] = Form(None),
    text: Optional[str] = Form(None),
    tracking_id: Optional[str] = Form(None),
    audio: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    try:
        return await ivr_service.handle_callback(
            db,
            session_id=session_id,
            phone_number=phone_number,
            provider=provider,
            digits=digits,
            text=text,
            tracking_id=tracking_id,
            audio=audio,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/session/{session_id}")
async def get_session(session_id: str, db: Session = Depends(get_db)):
    session = ivr_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="IVR session not found")
    return session


@router.get("/sessions")
async def get_recent_sessions(
    limit: int = 20,
    current_user: User = Depends(get_officer),
    db: Session = Depends(get_db),
):
    return ivr_service.recent_sessions(db, limit)


@router.post("/twilio/call")
async def place_twilio_call(payload: OutboundCall, current_user: User = Depends(get_officer)):
    base_url = settings.PUBLIC_BASE_URL.rstrip("/")
    if base_url.startswith("http://127.0.0.1") or base_url.startswith("http://localhost"):
        raise HTTPException(status_code=400, detail="Set PUBLIC_BASE_URL to your public ngrok URL before placing Twilio calls.")
    try:
        result = await ivr_service.provider("twilio").place_call(payload.to_number, public_url("/ivr/twilio/incoming"))
        return {"message": "Call initiated", "call_sid": result.get("sid"), "status": result.get("status")}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/twilio/test-call")
async def place_twilio_test_call(payload: OutboundCall, current_user: User = Depends(get_officer)):
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        "<Say>KrishiMitra test call is working. This call does not use your public webhook tunnel.</Say>"
        "</Response>"
    )
    try:
        result = await ivr_service.provider("twilio").place_twiml_call(payload.to_number, twiml)
        return {"message": "Test call initiated", "call_sid": result.get("sid"), "status": result.get("status")}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/twilio/demo-call")
async def place_twilio_demo_call(payload: OutboundCall, current_user: User = Depends(get_officer)):
    twiml = interactive_demo_menu_twiml("Welcome to KrishiMitra phone demo. You can use keypad or voice.")
    try:
        result = await ivr_service.provider("twilio").place_twiml_call(payload.to_number, twiml)
        return {"message": "Demo call initiated", "call_sid": result.get("sid"), "status": result.get("status")}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/twilio/demo-scenario-call")
async def place_twilio_demo_scenario_call(payload: DemoScenarioCall, current_user: User = Depends(get_officer)):
    scenario = payload.scenario.strip().lower()
    message = DEMO_SCENARIOS.get(scenario)
    if not message:
        raise HTTPException(status_code=400, detail="Invalid scenario. Use disease, grievance, scheme, or weather.")
    try:
        result = await ivr_service.provider("twilio").place_twiml_call(payload.to_number, demo_twiml(message))
        return {
            "message": f"{scenario.title()} demo call initiated",
            "call_sid": result.get("sid"),
            "status": result.get("status"),
            "scenario": scenario,
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.api_route("/twilio/ping", methods=["GET", "POST"])
async def twilio_ping():
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        "<Say>KrishiMitra webhook reached successfully.</Say>"
        "</Response>"
    )
    return twiml_response(twiml)


@router.api_route("/twilio/demo", methods=["GET", "POST"])
async def twilio_demo():
    return twiml_response(interactive_demo_menu_twiml("Welcome to KrishiMitra. This demo supports both keypad and voice."))


@router.api_route("/twilio/interactive-demo", methods=["GET", "POST"])
async def twilio_interactive_demo():
    return twiml_response(interactive_demo_menu_twiml("Welcome to KrishiMitra. This demo supports both keypad and voice."))


@router.api_route("/twilio/interactive-demo/handle", methods=["GET", "POST"])
async def twilio_interactive_demo_handle(
    Digits: Optional[str] = Form(None),
    SpeechResult: Optional[str] = Form(None),
):
    scenario = detect_demo_choice(Digits, SpeechResult)
    if scenario:
        message = DEMO_SCENARIOS[scenario]
        heard = f"You selected {scenario}."
        if SpeechResult:
            heard = f"I heard: {SpeechResult}. You selected {scenario}."
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f"{say(heard)}"
            f"{say(message)}"
            "<Pause length=\"1\"/>"
            f"{say('To try another option, use keypad or say disease, grievance, scheme, or weather.')}"
            f'<Redirect method="POST">{escape(public_url("/ivr/twilio/interactive-demo"))}</Redirect>'
            "</Response>"
        )
        return twiml_response(twiml)

    return twiml_response(interactive_demo_menu_twiml("Sorry, I could not understand that input."))


@router.api_route("/twilio/demo/menu", methods=["GET", "POST"])
async def twilio_demo_menu(Digits: Optional[str] = Form(None)):
    digit = (Digits or "").strip()
    if digit == "1":
        message = (
            "For crop issues, check the affected leaves, roots, and nearby plants first. "
            "Avoid spraying before rain, and contact the local agriculture officer if the disease is spreading quickly."
        )
    elif digit == "2":
        message = (
            "Your grievance demo has been received. Keep your application number, Aadhaar, bank details, and land record ready. "
            "A demo tracking number is D M O 2 0 2 6 1 2 3."
        )
    elif digit == "3":
        message = (
            "For scheme help, keep Aadhaar, bank passbook, land record, and mobile number ready. "
            "Eligibility depends on the scheme, state, land ownership, and farmer category."
        )
    else:
        message = "Invalid input. The demo supports 1 for crop advice, 2 for grievance, and 3 for scheme help."

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"{say(message)}"
        f'<Gather input="dtmf speech" numDigits="1" timeout="10" speechTimeout="auto" language="en-IN" action="{escape(public_url("/ivr/twilio/interactive-demo/handle"))}" method="POST">'
        f"{say('Press 1 for crop advice, 2 for grievance, 3 for scheme help, or 4 for weather. You can also say the option name.')}"
        "</Gather>"
        f"{say('Thank you for calling KrishiMitra demo.')}"
        "</Response>"
    )
    return twiml_response(twiml)


@router.api_route("/twilio/incoming", methods=["GET", "POST"])
async def twilio_incoming(
    From: Optional[str] = Form(None),
    To: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    return await _twilio_incoming_response(From, To, db)


async def _twilio_incoming_response(From: Optional[str], To: Optional[str], db: Session) -> Response:
    print(f"Twilio incoming webhook reached. From={From}, To={To}")
    try:
        phone_number = From or To or "unknown-twilio-caller"
        action = await ivr_service.incoming_call(db, phone_number, "twilio")
        twiml = ivr_service.provider("twilio").to_twiml(
            _action_from_rendered(action),
            session_id=action["session"]["session_id"],
            callback_url=public_url("/ivr/twilio/callback"),
            public_base_url=public_asset_base_url(),
        )
    except Exception as error:
        print(f"Twilio incoming failed: {error}")
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            "<Say>KrishiMitra server received the call, but the IVR had an internal error. Please check backend logs.</Say>"
            "</Response>"
        )
    return twiml_response(twiml)


@router.post("/twilio/callback")
async def twilio_callback(
    session_id: str,
    From: Optional[str] = Form(None),
    Digits: Optional[str] = Form(None),
    RecordingUrl: Optional[str] = Form(None),
    SpeechResult: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    print(f"Twilio callback reached. session_id={session_id}, From={From}, Digits={Digits}, RecordingUrl={RecordingUrl}")
    try:
        text = SpeechResult
        if RecordingUrl and not text:
            text = await _transcribe_twilio_recording(session_id, RecordingUrl, db)

        action = await ivr_service.handle_callback(
            db,
            session_id=session_id,
            phone_number=From,
            provider="twilio",
            digits=Digits,
            text=text,
        )
        twiml = ivr_service.provider("twilio").to_twiml(
            _action_from_rendered(action),
            session_id=action["session"]["session_id"],
            callback_url=public_url("/ivr/twilio/callback"),
            public_base_url=public_asset_base_url(),
        )
    except Exception as error:
        print(f"Twilio callback failed: {error}")
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            "<Say>KrishiMitra received your input, but could not continue. Please check backend logs.</Say>"
            "</Response>"
        )
    return twiml_response(twiml)


async def _read_incoming_payload(request: Request) -> IncomingCall:
    if request.method == "GET":
        phone_number = request.query_params.get("From") or request.query_params.get("phone_number") or "browser-test"
        provider = request.query_params.get("provider") or "twilio"
        return IncomingCall(phone_number=phone_number, provider=provider)

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        return IncomingCall(
            phone_number=body.get("phone_number") or body.get("From") or body.get("To") or "unknown-caller",
            provider=body.get("provider") or "mock",
        )

    form = await request.form()
    provider = str(form.get("provider") or "twilio")
    return IncomingCall(
        phone_number=str(form.get("From") or form.get("To") or "unknown-twilio-caller"),
        provider=provider,
    )


def _action_from_rendered(rendered: dict):
    from app.services.ivr.ivr_models import IvrAction

    return IvrAction(
        type="prompt",
        prompt=rendered.get("prompt", ""),
        audio_url=rendered.get("audio_url"),
        collect_digits=rendered.get("action") == "collect_digits",
        max_digits=rendered.get("max_digits", 1),
        record=rendered.get("action") == "record",
        next_state=rendered.get("next_state"),
        metadata=rendered.get("metadata") or {},
    )


async def _transcribe_twilio_recording(session_id: str, recording_url: str, db: Session) -> str:
    session = ivr_service.get_session(db, session_id)
    language = session.get("language") if session else "ta"
    audio_url = recording_url if recording_url.endswith(".wav") else f"{recording_url}.wav"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(audio_url, auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN))
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Could not download Twilio recording: {response.text}")
    lang_code = {"ta": "ta-IN", "kn": "kn-IN", "en": "en-IN"}.get(language or "ta", "ta-IN")
    result = await transcribe_audio(response.content, lang_code, "twilio-recording.wav")
    return result.get("transcript") or ""
