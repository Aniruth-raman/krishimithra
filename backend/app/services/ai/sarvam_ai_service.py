import base64
import json
import re
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings


SARVAM_BASE_URL = "https://api.sarvam.ai"

LANGUAGE_NAMES = {
    "en": "English",
    "ta": "Tamil",
    "hi": "Hindi",
    "kn": "Kannada",
    "en-IN": "English",
    "ta-IN": "Tamil",
    "hi-IN": "Hindi",
    "kn-IN": "Kannada",
}

SYSTEM_PROMPT_FARMER = """You are KrishiMitra AI, an enterprise-grade agricultural decision-support assistant for Indian farmers, FPOs, and field extension teams.

Core mandate:
- Provide technically sound, practical, and locally relevant agricultural guidance for India.
- Cover crop health, pest and disease triage, fertilizer and irrigation planning, weather-risk decisions, government schemes, market/grievance navigation, and yield improvement.
- Prioritize South Indian farming contexts when relevant, including rice, sugarcane, banana, cotton, groundnut, millets, pulses, coconut, and vegetables.

Response quality standard:
- Answer only in the requested language and keep the tone respectful, confident, and farmer-friendly.
- Sound natural, like a knowledgeable agriculture officer speaking to the farmer, not like a template.
- Start with the most useful answer, then give clear next actions.
- Use short paragraphs. Use bullets only when they genuinely make the answer easier to follow.
- Do not use markdown decorations, bold markers, hash headings, tables, or robotic labels unless the user asks for a formal report.
- Avoid over-polished corporate phrasing, long introductions, and repeated disclaimers.
- Ask for missing critical details only when they materially change the recommendation, such as crop, stage, district, irrigation status, symptoms, acreage, or recent pesticide/fertilizer use.
- Distinguish facts from assumptions. If context is incomplete, state the assumption briefly and provide a safe next step.
- Do not fabricate live weather, market prices, scheme rules, laboratory results, pesticide labels, or official deadlines.

Agronomy and safety rules:
- For pests, diseases, and nutrient problems, provide symptom-based triage and integrated pest management first: field inspection, sanitation, water management, resistant varieties, traps, biological options, and threshold-based action.
- Give chemical pesticide, fungicide, herbicide, fertilizer, or growth-regulator dosage only when the product, crop, target issue, formulation, and local label context are clear. Otherwise advise label verification and local agriculture officer/KVK confirmation.
- Mention pre-harvest interval, protective equipment, wind/rain precautions, and safe storage whenever chemical spraying is discussed.
- Recommend urgent escalation to the agriculture department, KVK, veterinary/medical help, or emergency services when there is severe crop loss, suspected poisoning, animal/human health risk, unknown chemical exposure, or rapidly spreading disease.

Government and grievance rules:
- For schemes, clearly classify eligibility as eligible, not eligible, or needs verification. Explain the reason, documents, benefits, and next official step.
- For grievances, provide a professional escalation path, documents to collect, and how to phrase the complaint without blaming unsupported parties.
"""


def _language_name(language: str) -> str:
    return LANGUAGE_NAMES.get(language, "English")


def _language_instruction(language: str) -> str:
    return (
        f"Response language: {_language_name(language)} only. "
        "Use natural local phrasing, translate headings when possible, and keep official scheme/product names unchanged when translation may reduce clarity."
    )


def _basic_sentence_format(text: str, language: str = "en") -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return ""
    if language in {"en", "en-IN"}:
        parts = re.split(r"(?<=[.!?])\s+", cleaned)
        formatted_parts = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            part = part[0].upper() + part[1:] if part else part
            if part[-1] not in ".?!":
                part += "?"
            formatted_parts.append(part)
        return " ".join(formatted_parts)
    if cleaned[-1] not in ".?!?":
        cleaned += "."
    return cleaned


def _clean_ai_response(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*[*]\s+", "- ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


async def format_transcript_text(text: str, language: str = "en", use_ai: bool = True) -> str:
    fallback = _basic_sentence_format(text, language)
    if not use_ai or not settings.SARVAM_API_KEY or not settings.VOICE_ENABLE_AI_FORMATTING:
        return fallback

    try:
        content = await _sarvam_chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a transcript normalization engine for an agricultural voice assistant. "
                        "Correct only punctuation, sentence boundaries, capitalization, and obvious spacing. "
                        "Preserve the speaker's meaning, language, numbers, crop names, locations, and uncertainty exactly. "
                        "Do not add facts, infer missing words, translate, summarize, or answer the query. "
                        f"{_language_instruction(language)}"
                    ),
                },
                {"role": "user", "content": text},
            ],
            max_tokens=220,
            temperature=0,
        )
        formatted = content.strip().strip('"')
        return formatted or fallback
    except Exception as error:
        print(f"Sarvam format_transcript_text failed: {error}")
        return fallback


def _sarvam_headers() -> Dict[str, str]:
    return {
        "api-subscription-key": settings.SARVAM_API_KEY,
        "Content-Type": "application/json",
    }


def _extract_chat_content(payload: Dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if choices:
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
    if isinstance(payload.get("content"), str):
        return payload["content"]
    if isinstance(payload.get("text"), str):
        return payload["text"]
    return ""


async def _sarvam_chat(
    messages: List[Dict[str, str]],
    max_tokens: int = 2048,
    temperature: float = 0.4,
) -> str:
    if not settings.SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY is empty in backend/app/.env")

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{SARVAM_BASE_URL}/v1/chat/completions",
            headers=_sarvam_headers(),
            json={
                "model": settings.SARVAM_CHAT_MODEL,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "reasoning_effort": None,
            },
        )
        response.raise_for_status()
        content = _extract_chat_content(response.json()).strip()
        if not content:
            raise RuntimeError("Sarvam returned an empty chat response")
        return content


def _friendly_sarvam_error(error: Exception, language: str) -> str:
    detail = str(error)
    if "SARVAM_API_KEY" in detail:
        messages = {
            "ta": "Sarvam API key அமைக்கப்படவில்லை. backend/app/.env கோப்பில் SARVAM_API_KEY சேர்த்து backend ஐ restart செய்யவும்.",
            "hi": "Sarvam API key सेट नहीं है। backend/app/.env में SARVAM_API_KEY जोड़कर backend restart करें।",
            "kn": "Sarvam API key ಹೊಂದಿಸಲಾಗಿಲ್ಲ. backend/app/.env ನಲ್ಲಿ SARVAM_API_KEY ಸೇರಿಸಿ backend ಅನ್ನು restart ಮಾಡಿ.",
            "en": "Sarvam API key is not configured. Add SARVAM_API_KEY in backend/app/.env and restart the backend.",
        }
        return messages.get(language, messages["en"])

    if "401" in detail or "403" in detail or "unauthorized" in detail.lower() or "forbidden" in detail.lower():
        messages = {
            "ta": "Sarvam API key தவறாக உள்ளது அல்லது இந்த API க்கு அனுமதி இல்லை. key மற்றும் subscription ஐ சரிபார்த்து backend ஐ restart செய்யவும்.",
            "hi": "Sarvam API key गलत है या इस API की अनुमति नहीं है। key/subscription जाँचें और backend restart करें।",
            "kn": "Sarvam API key ತಪ್ಪಾಗಿದೆ ಅಥವಾ ಈ API ಗೆ ಅನುಮತಿ ಇಲ್ಲ. key/subscription ಪರಿಶೀಲಿಸಿ backend restart ಮಾಡಿ.",
            "en": "Sarvam API key is invalid or not allowed for this API. Check the key/subscription and restart the backend.",
        }
        return messages.get(language, messages["en"])

    messages = {
        "ta": "Sarvam AI request தோல்வியடைந்தது. Backend terminal இல் error details பார்க்கவும்.",
        "hi": "Sarvam AI request failed. Backend terminal में error details देखें।",
        "kn": "Sarvam AI request ವಿಫಲವಾಯಿತು. Backend terminal ನಲ್ಲಿ error details ನೋಡಿ.",
        "en": "Sarvam AI request failed. Check the backend terminal for details.",
    }
    return messages.get(language, messages["en"])


async def diagnose_sarvam() -> Dict[str, Any]:
    if not settings.SARVAM_API_KEY:
        return {
            "configured": False,
            "ok": False,
            "provider": "sarvam",
            "model": settings.SARVAM_CHAT_MODEL,
            "error_type": "missing_key",
            "message": "SARVAM_API_KEY is empty in backend/app/.env.",
        }

    try:
        message = await _sarvam_chat(
            messages=[{"role": "user", "content": "Reply with OK"}],
            max_tokens=10,
            temperature=0,
        )
        return {
            "configured": True,
            "ok": True,
            "provider": "sarvam",
            "model": settings.SARVAM_CHAT_MODEL,
            "message": message,
        }
    except Exception as error:
        return {
            "configured": True,
            "ok": False,
            "provider": "sarvam",
            "model": settings.SARVAM_CHAT_MODEL,
            "error_type": type(error).__name__,
            "message": str(error),
        }


async def classify_intent(message: str, fast: bool = False) -> str:
    if fast or not settings.SARVAM_API_KEY:
        return _fallback_intent(message)

    try:
        content = await _sarvam_chat(
            messages=[
                {
                    "role": "system",
                    "content": """You are an intent classifier for KrishiMitra AI.

Classify the farmer's latest message into exactly one category:
- disease: crop disease, pest, weed, nutrient deficiency, leaf/fruit/root/stem symptoms, diagnosis, treatment, pesticide/fungicide questions
- weather: rain, wind, humidity, temperature, spraying window, irrigation timing based on weather, storm/drought/flood risk
- scheme: government schemes, subsidies, PM-KISAN, PMFBY, KCC, eligibility, documents, application status
- grievance: complaint filing, delayed payment, rejected application, insurance claim dispute, official escalation, market/government service issue
- yield: fertilizer schedule, irrigation schedule, spacing, crop stage management, productivity improvement, soil health, cultivation practice
- general: greetings, unclear requests, app help, or anything not covered above

Return only one lowercase category word. No punctuation, explanation, or extra text.""",
                },
                {"role": "user", "content": message},
            ],
            max_tokens=10,
            temperature=0,
        )
        intent = content.strip().lower()
        return intent if intent in {"disease", "weather", "scheme", "grievance", "yield", "general"} else "general"
    except Exception as error:
        print(f"Sarvam classify_intent failed: {error}")
        return _fallback_intent(message)


def _fallback_intent(message: str) -> str:
    msg = message.lower()
    if any(word in msg for word in ["disease", "pest", "leaf", "yellow", "rot", "fungus", "virus", "நோய்", "ರೋಗ", "बीमारी", "कीट"]):
        return "disease"
    if any(word in msg for word in ["weather", "rain", "spray", "wind", "மழை", "ಮಳೆ", "बारिश", "मौसम"]):
        return "weather"
    if any(word in msg for word in ["scheme", "kisan", "subsidy", "yojana", "திட்டம்", "ಯೋಜನೆ", "योजना", "सब्सिडी"]):
        return "scheme"
    if any(word in msg for word in ["complaint", "grievance", "delay", "problem", "புகார்", "ದೂರು", "शिकायत"]):
        return "grievance"
    if any(word in msg for word in ["yield", "fertilizer", "water", "irrigation", "விளைச்சல்", "ಇಳುವರಿ", "उपज", "खाद"]):
        return "yield"
    return "general"


async def chat_with_ai(
    message: str,
    history: List[Dict[str, str]],
    language: str = "ta",
    context: Optional[Dict[str, Any]] = None,
    channel: str = "chat",
) -> str:
    system = f"{SYSTEM_PROMPT_FARMER}\n\n{_language_instruction(language)}"
    if channel in {"ivr", "voice"}:
        system += """

Voice response contract:
- The response will be spoken aloud in real time, so optimize for speed and clarity.
- Use 2 to 4 short, natural sentences with no markdown, tables, symbols, or numbered lists.
- Lead with the answer in the first sentence, then give one or two practical actions.
- Avoid long introductions, repeated disclaimers, and deep background explanation.
- Ask only one follow-up question when the answer would otherwise be unsafe or misleading.
- If the issue is urgent, uncertain, chemical-related, or severe, recommend local agriculture officer or KVK verification."""
    if context:
        system += f"\n\nFarmer context: {json.dumps(context, ensure_ascii=False)}"

    try:
        messages = [{"role": "system", "content": system}]
        messages.extend(history[-10:])
        messages.append({"role": "user", "content": message})
        max_tokens = 320 if channel in {"ivr", "voice"} else 1400
        temperature = 0.35 if channel in {"ivr", "voice"} else 0.55
        content = await _sarvam_chat(messages=messages, max_tokens=max_tokens, temperature=temperature)
        return _clean_ai_response(content)
    except Exception as error:
        print(f"Sarvam chat_with_ai failed: {error}")
        return _friendly_sarvam_error(error, language)


async def analyze_crop_image(image_path: str, crop_type: Optional[str] = None) -> Dict[str, Any]:
    try:
        with open(image_path, "rb") as image_file:
            base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as error:
        print(f"Image read failed: {error}")
    return _mock_disease_analysis(crop_type)


async def check_scheme_eligibility(
    scheme_name: str,
    state: str,
    land_ownership: str,
    farmer_category: str,
    annual_income: float,
    language: str = "ta",
) -> Dict[str, Any]:
    rule_result = _rule_based_scheme_check(scheme_name, state, land_ownership, farmer_category, annual_income)
    if rule_result:
        return rule_result

    try:
        prompt = f"""Evaluate eligibility for this Indian agricultural scheme using a high-accuracy, official-process-oriented standard.
Scheme: {scheme_name}
State: {state}
Land ownership: {land_ownership}
Farmer category: {farmer_category}
Annual income: {annual_income}

Return only valid JSON with these keys:
is_eligible (true, false, or null when verification is required),
eligibility_status ("eligible", "not_eligible", or "requires_verification"),
eligibility_reason,
benefits,
required_documents (array),
alternative_schemes (array),
application_steps,
verification_notes.

Do not invent state-specific rules, deadlines, benefit amounts, or portal status. If the supplied details are insufficient, mark eligibility_status as "requires_verification" and explain what to verify.
All text values must be in {_language_name(language)}."""
        content = await _sarvam_chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior Indian agricultural scheme eligibility analyst. "
                        "Use cautious, official-process-oriented reasoning and return strict JSON only. "
                        f"{_language_instruction(language)}"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=2048,
            temperature=0.2,
        )
        if content.startswith("```"):
            content = content.strip("`").replace("json", "", 1).strip()
        return json.loads(content)
    except Exception as error:
        print(f"Sarvam check_scheme_eligibility failed: {error}")
        return _mock_scheme_check(scheme_name, annual_income, language)


def _normalise(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _ownership_type(land_ownership: Optional[str]) -> str:
    ownership = _normalise(land_ownership)
    if any(word in ownership for word in ["own", "owner", "owned", "landholder", "patta"]):
        return "owner"
    if any(word in ownership for word in ["tenant", "lease", "lessee", "share", "oral"]):
        return "tenant"
    if any(word in ownership for word in ["landless", "none", "no land"]):
        return "landless"
    return "unknown"


def _eligibility_result(
    scheme_name: str,
    status: Optional[bool],
    reason: str,
    benefits: str,
    documents: List[str],
    steps: str,
    alternatives: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "is_eligible": status,
        "eligibility_status": "eligible" if status is True else "not_eligible" if status is False else "requires_verification",
        "eligibility_reason": reason,
        "benefits": benefits,
        "required_documents": documents,
        "alternative_schemes": alternatives or ["Kisan Credit Card", "PM Fasal Bima Yojana", "Soil Health Card Scheme"],
        "application_steps": steps,
        "scheme_name": scheme_name,
    }


def _rule_based_scheme_check(
    scheme_name: str,
    state: Optional[str],
    land_ownership: Optional[str],
    farmer_category: Optional[str],
    annual_income: Optional[float],
) -> Optional[Dict[str, Any]]:
    scheme = _normalise(scheme_name)
    state_value = _normalise(state)
    owner_type = _ownership_type(land_ownership)
    category = _normalise(farmer_category)

    if "pm-kisan" in scheme or "pm kisan" in scheme or "samman nidhi" in scheme:
        if owner_type in {"tenant", "landless"}:
            return _eligibility_result(
                "PM-KISAN",
                False,
                "PM-KISAN is for landholding farmer families. Tenant/sharecropper or landless entries usually do not qualify unless land is recorded in the farmer family's name.",
                "Income support of Rs 6,000 per year in three instalments to eligible landholding farmer families.",
                ["Aadhaar", "Land ownership record", "Bank account", "Mobile number", "e-KYC"],
                "Verify land records and exclusion status on the official PM-KISAN portal or through the local agriculture office.",
            )
        if owner_type == "owner":
            return _eligibility_result(
                "PM-KISAN",
                None,
                "The farmer appears to meet the landholding requirement. Final eligibility also depends on exclusion checks such as institutional landholding, income-tax payer status, government service, pension, constitutional post, and registered professional status.",
                "Income support of Rs 6,000 per year in three instalments to eligible landholding farmer families.",
                ["Aadhaar", "Land ownership record", "Bank account", "Mobile number", "e-KYC"],
                "Complete e-KYC and verify beneficiary status through PM-KISAN or the local agriculture office.",
            )
        return _eligibility_result(
            "PM-KISAN",
            None,
            "Land ownership is required to decide PM-KISAN eligibility. Add whether the farmer owns recorded agricultural land.",
            "Income support of Rs 6,000 per year in three instalments to eligible landholding farmer families.",
            ["Aadhaar", "Land ownership record", "Bank account", "Mobile number", "e-KYC"],
            "Collect land record and exclusion details, then verify on the PM-KISAN portal.",
        )

    if "fasal bima" in scheme or "pmfby" in scheme or "crop insurance" in scheme:
        if owner_type == "landless":
            status = False
            reason = "PMFBY needs insurable interest in a notified crop on notified land. A landless farmer without cultivation rights or crop documents is not eligible for that plot."
        elif owner_type in {"owner", "tenant"}:
            status = None
            reason = "The farmer may be eligible if the crop, area, season, and cut-off date are notified and the farmer can prove insurable interest. Tenant/sharecropper farmers need state-permitted documents."
        else:
            status = None
            reason = "PMFBY eligibility depends on crop, season, notified area, and proof of cultivation. Add land/cultivation details for a better decision."
        if state_value in {"karnataka", "gujarat"}:
            reason += " Direct NCIP enrollment may not apply in this state; use the state enrollment portal/process."
        return _eligibility_result(
            "PM Fasal Bima Yojana",
            status,
            reason,
            "Crop insurance cover against notified crop loss, subject to state/season notification and premium payment.",
            ["Aadhaar", "Bank passbook", "Land record/LPC/lease or sharecropper document", "Sowing certificate or crop declaration", "Mobile number"],
            "Check the current season notification, enroll before the cut-off date through the portal, CSC, bank, or state process.",
        )

    if "kisan credit" in scheme or "kcc" in scheme:
        if owner_type in {"owner", "tenant"}:
            status = None
            reason = "The farmer is in an eligible cultivator category for KCC. Final approval depends on bank appraisal, crop plan, documents, and credit history."
        elif owner_type == "landless":
            status = None
            reason = "Landless farmers may access KCC only when they have eligible allied activities or apply through SHG/JLG/tenant cultivation arrangements accepted by the bank."
        else:
            status = None
            reason = "KCC supports owner cultivators, tenant farmers, oral lessees, sharecroppers, and SHG/JLG farmers. Add cultivation/tenant details for a stronger decision."
        return _eligibility_result(
            "Kisan Credit Card",
            status,
            reason,
            "Short-term crop credit and allied activity credit through banks, subject to sanctioned limit.",
            ["Identity proof", "Address proof", "Land/cultivation document", "Crop details", "Bank account", "Photograph"],
            "Apply at the bank branch or Kisan Rin portal with cultivation and identity documents.",
        )

    if "soil health" in scheme:
        return _eligibility_result(
            "Soil Health Card Scheme",
            True,
            "The Soil Health Card service is meant to provide soil nutrient status and crop-wise nutrient advice for farmer holdings.",
            "Soil test based advisory for nutrient management and fertilizer use.",
            ["Farmer details", "Mobile number", "Holding/plot details", "Soil sample details"],
            "Contact the agriculture department/soil testing lab or use the Soil Health Card portal process for sampling.",
        )

    if "sinchayee" in scheme or "pmksy" in scheme or "irrigation" in scheme:
        return _eligibility_result(
            "Pradhan Mantri Krishi Sinchayee Yojana",
            None,
            "Eligibility depends on the state component, local project, land/cultivation status, and irrigation asset proposed. The current form does not capture those details.",
            "Support for irrigation access, water-use efficiency, and micro-irrigation depending on state/project rules.",
            ["Land/cultivation document", "Aadhaar", "Bank account", "Project estimate or irrigation asset details", "State application form"],
            "Check the district agriculture/horticulture office for the active PMKSY component and subsidy rules.",
        )

    if "enam" in scheme or "national agriculture market" in scheme:
        return _eligibility_result(
            "National Agriculture Market (eNAM)",
            None,
            "A farmer can usually register to trade through an eNAM-enabled mandi, but access depends on the crop, mandi/APMC, state process, and produce details.",
            "Online market access, price discovery, and trading support through participating mandis.",
            ["Farmer identity", "Bank account", "Mobile number", "Produce details", "Mandi/APMC registration if required"],
            "Register through the eNAM portal or participating mandi and verify crop/mandi availability.",
        )

    if "krushak" in scheme or "kalia" in scheme:
        if state_value not in {"odisha", "orissa"}:
            return _eligibility_result(
                "Krushak Yojana",
                False,
                "This is treated as an Odisha state farmer-support scheme. The entered state is outside Odisha, so the farmer should check their own state's scheme instead.",
                "State-specific farmer livelihood or income support depending on Odisha rules.",
                ["Aadhaar", "Bank account", "Residence proof", "Farmer/cultivator details"],
                "Check the Odisha scheme portal/local agriculture office if the farmer is an Odisha resident.",
            )
        status = None if category not in {"large", "commercial"} else False
        reason = "The farmer may qualify under Odisha state rules if they are a small/marginal cultivator, sharecropper, or covered landless agricultural household. Final checks require residence, category, and exclusion details."
        if status is False:
            reason = "Large/commercial farmer category may not meet the intended small/marginal or vulnerable farmer support criteria."
        return _eligibility_result(
            "Krushak Yojana",
            status,
            reason,
            "State-specific livelihood/income assistance depending on current Odisha rules.",
            ["Aadhaar", "Bank account", "Residence proof", "Farmer/cultivator details", "Category proof if applicable"],
            "Verify through the Odisha scheme portal or local agriculture office.",
        )

    return None


async def get_weather_advisory(
    crop_type: str,
    district: str,
    query: str,
    language: str = "ta",
) -> str:
    weather = {
        "temperature": 31,
        "humidity": 72,
        "rainfall_mm": 4,
        "wind_speed_kmh": 12,
        "forecast_3days": "Light rain is possible in the next 2 days.",
    }

    try:
        prompt = f"""Prepare a weather-risk advisory for the farmer.
Farmer query: {query}
District: {district}
Crop: {crop_type}
Current weather: Temperature {weather['temperature']}°C, humidity {weather['humidity']}%, rainfall {weather['rainfall_mm']} mm, wind {weather['wind_speed_kmh']} km/h.
3-day forecast: {weather['forecast_3days']}

Give a concise but technically strong advisory:
- State the decision first, especially whether to irrigate, spray, delay spraying, drain water, or monitor.
- Explain the weather risk in farmer-friendly terms.
- Include safe spray guidance when relevant: rain gap, wind caution, protective equipment, and label verification.
- Do not claim this is live weather; use only the weather values provided above.
{_language_instruction(language)}"""
        content = await _sarvam_chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior agrometeorology advisor for Indian farming conditions. "
                        "Provide cautious, actionable, crop-stage-aware weather advice without inventing unavailable forecast data."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=1200,
            temperature=0.4,
        )
        return _clean_ai_response(content)
    except Exception as error:
        print(f"Sarvam get_weather_advisory failed: {error}")
        return _mock_weather_advisory(crop_type, district, weather, language)


async def classify_grievance(description: str) -> str:
    keywords = {
        "Subsidy Delay": ["subsidy", "delayed", "payment", "money", "fund"],
        "Crop Loss": ["crop loss", "flood", "drought", "damage", "destroyed"],
        "Insurance": ["insurance", "claim", "premium", "coverage"],
        "Irrigation": ["water", "canal", "irrigation", "drought", "pump"],
        "Market Rate Issue": ["price", "market", "msp", "rate", "buyer"],
    }
    desc_lower = description.lower()
    for category, words in keywords.items():
        if any(word in desc_lower for word in words):
            return category
    return "Subsidy Delay"


def _mock_weather_advisory(crop_type: str, district: str, weather: Dict[str, Any], language: str) -> str:
    if language == "ta":
        return f"{district} பகுதியில் தற்போது {weather['temperature']}°C வெப்பநிலை மற்றும் {weather['humidity']}% ஈரப்பதம் உள்ளது. {crop_type} பயிரில் மழை வாய்ப்பு உள்ளதால் பூச்சிக்கொல்லி தெளிப்பதை தவிர்க்கவும்."
    if language == "hi":
        return f"{district} में अभी तापमान {weather['temperature']}°C और आर्द्रता {weather['humidity']}% है। {crop_type} के लिए बारिश की संभावना होने पर कीटनाशक छिड़काव टालें।"
    if language == "kn":
        return f"{district} ಪ್ರದೇಶದಲ್ಲಿ ಈಗ {weather['temperature']}°C ತಾಪಮಾನ ಮತ್ತು {weather['humidity']}% ಆರ್ದ್ರತೆ ಇದೆ. {crop_type} ಬೆಳೆಗೆ ಮಳೆಯ ಸಾಧ್ಯತೆ ಇದ್ದರೆ ಕೀಟನಾಶಕ ಸಿಂಪಡಣೆ ತಪ್ಪಿಸಿ."
    return f"Weather in {district}: {weather['temperature']}°C and {weather['humidity']}% humidity. For {crop_type}, avoid pesticide spraying if rain is expected."


def _mock_disease_analysis(crop_type: Optional[str]) -> Dict[str, Any]:
    return {
        "disease_name": "Leaf Blight",
        "pest_name": "Aphids",
        "severity": "medium",
        "confidence_score": 0.82,
        "description": f"The {crop_type or 'crop'} shows symptoms similar to leaf blight with possible minor aphid infestation. Sarvam chat is text-only here, so this image result is a demo fallback.",
        "treatment": "Remove affected leaves, improve airflow, avoid excess irrigation, and consult a local agriculture officer for the correct fungicide dosage.",
        "preventive_measures": "Maintain spacing, avoid overhead irrigation, use resistant varieties, and inspect leaves weekly.",
    }


def _mock_scheme_check(scheme_name: str, annual_income: float, language: str) -> Dict[str, Any]:
    annual_income = annual_income or 0
    is_eligible = annual_income < 200000
    if language == "ta":
        reason = f"உங்கள் ஆண்டு வருமானம் ₹{annual_income:,.0f}. {scheme_name} திட்டத்திற்கு நீங்கள் {'தகுதி பெறுகிறீர்கள்' if is_eligible else 'தகுதி பெறவில்லை'} என்று முதற்கட்டமாக தெரிகிறது."
    elif language == "hi":
        reason = f"आपकी वार्षिक आय ₹{annual_income:,.0f} है। {scheme_name} के लिए आप {'योग्य हैं' if is_eligible else 'योग्य नहीं हैं'}।"
    elif language == "kn":
        reason = f"ನಿಮ್ಮ ವಾರ್ಷಿಕ ಆದಾಯ ₹{annual_income:,.0f}. {scheme_name} ಯೋಜನೆಗೆ ನೀವು {'ಅರ್ಹರಾಗಿದ್ದೀರಿ' if is_eligible else 'ಅರ್ಹರಲ್ಲ'} ಎಂದು ಪ್ರಾಥಮಿಕವಾಗಿ ಕಾಣುತ್ತದೆ."
    else:
        reason = f"Based on annual income of ₹{annual_income:,.0f}, you {'appear eligible' if is_eligible else 'do not appear eligible'} for {scheme_name}."

    return {
        "is_eligible": is_eligible,
        "eligibility_reason": reason,
        "benefits": "Benefits depend on the scheme rules and state implementation.",
        "required_documents": ["Aadhaar Card", "Land Records", "Bank Account Details", "Mobile Number"],
        "alternative_schemes": ["PM Fasal Bima Yojana", "Kisan Credit Card", "Soil Health Card Scheme"],
        "application_steps": "Visit the nearest CSC/agriculture office or official scheme portal with documents.",
    }
