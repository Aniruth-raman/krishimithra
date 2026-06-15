import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from app.config import settings


DEFAULT_INDIAN_LOCATIONS = {
    "ahmedabad", "bengaluru", "bangalore", "bhopal", "bhubaneswar", "chandigarh",
    "chennai", "coimbatore", "cuttack", "delhi", "erode", "guntur", "guwahati",
    "hyderabad", "indore", "jaipur", "kochi", "kolkata", "lucknow", "madurai",
    "mangaluru", "mumbai", "mysuru", "nagpur", "nashik", "patna", "pune",
    "salem", "surat", "thanjavur", "tiruchirappalli", "trichy", "tirunelveli",
    "udaipur", "vijayawada", "visakhapatnam", "warangal",
    "ariyalur", "chengalpattu", "coimbatore", "cuddalore", "dharmapuri",
    "dindigul", "kallakurichi", "kanchipuram", "kanyakumari", "karur",
    "krishnagiri", "mayiladuthurai", "nagapattinam", "namakkal", "perambalur",
    "pudukkottai", "ramanathapuram", "ranipet", "sivaganga", "tenkasi",
    "theni", "thoothukudi", "tirupathur", "tiruppur", "tiruvallur",
    "tiruvannamalai", "tiruvarur", "vellore", "viluppuram", "virudhunagar",
}

LOCATION_PATTERNS = [
    r"\b(?:in|at|near|around|from|for)\s+([A-Za-z][A-Za-z .'-]{2,60})",
    r"\b(?:district|city|village)\s+([A-Za-z][A-Za-z .'-]{2,60})",
]

STOP_WORDS = {
    "today", "tomorrow", "weather", "rain", "spray", "pesticide", "crop", "field",
    "my", "the", "a", "an", "is", "are", "for", "now", "please", "should",
}


def _title_location(value: str) -> str:
    return " ".join(part.capitalize() for part in value.strip().split())


@lru_cache(maxsize=1)
def _configured_locations() -> set[str]:
    path_value = getattr(settings, "INDIAN_CITIES_PATH", "") or ""
    if not path_value:
        return set()
    path = Path(path_value)
    if not path.exists():
        return set()
    try:
        raw_text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            parsed = json.loads(raw_text)
            values = [str(item).strip().lower() for item in parsed if str(item).strip()] if isinstance(parsed, list) else []
        else:
            values = [
                line.strip().lower()
                for line in raw_text.splitlines()
                if line.strip()
            ]
        return set(values)
    except Exception as error:
        print(f"Could not load configured Indian cities file: {error}")
        return set()


def _all_locations() -> set[str]:
    return DEFAULT_INDIAN_LOCATIONS | _configured_locations()


def _candidate_phrases(text: str) -> Iterable[str]:
    for pattern in LOCATION_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            phrase = re.split(r"[,.?!;:]|\b(?:and|with|to|if|when|because)\b", match.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
            cleaned = re.sub(r"\s+", " ", phrase).strip(" -")
            if cleaned:
                yield cleaned


def extract_location(text: str) -> str | None:
    cleaned = (text or "").strip()
    if not cleaned:
        return None

    words = set(re.findall(r"[A-Za-z]+", cleaned.lower()))
    for location in sorted(_all_locations(), key=len, reverse=True):
        location_words = set(location.split())
        if location in cleaned.lower() or location_words.issubset(words):
            return _title_location(location)

    for phrase in _candidate_phrases(cleaned):
        phrase_words = [word for word in re.findall(r"[A-Za-z]+", phrase.lower()) if word not in STOP_WORDS]
        if not phrase_words:
            continue
        candidate = " ".join(phrase_words[:3])
        if len(candidate) >= 3:
            return _title_location(candidate)

    return None
