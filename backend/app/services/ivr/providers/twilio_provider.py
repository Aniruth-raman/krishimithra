from html import escape
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.services.ivr.ivr_models import IvrAction
from app.services.ivr.providers.mock_provider import MockTelephonyProvider


class TwilioProvider(MockTelephonyProvider):
    name = "twilio"

    def _require_config(self) -> None:
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not settings.TWILIO_FROM_NUMBER:
            raise ValueError("Twilio credentials and TWILIO_FROM_NUMBER must be configured in backend/app/.env")

    async def place_call(self, to_number: str, webhook_url: str) -> dict:
        self._require_config()
        url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Calls.json"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                data={
                    "To": to_number,
                    "From": settings.TWILIO_FROM_NUMBER,
                    "Url": webhook_url,
                    "Method": "POST",
                },
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            )
        if response.status_code >= 400:
            raise ValueError(f"Twilio call failed: {response.text}")
        return response.json()

    async def place_twiml_call(self, to_number: str, twiml: str) -> dict:
        self._require_config()
        url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Calls.json"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                data={
                    "To": to_number,
                    "From": settings.TWILIO_FROM_NUMBER,
                    "Twiml": twiml,
                },
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            )
        if response.status_code >= 400:
            raise ValueError(f"Twilio test call failed: {response.text}")
        return response.json()

    def to_twiml(self, action: IvrAction, *, session_id: str, callback_url: str, public_base_url: str) -> str:
        escaped_prompt = escape(action.prompt)
        play_or_say = self._play_or_say(action.audio_url, escaped_prompt, public_base_url)
        action_url = f"{callback_url}?{urlencode({'session_id': session_id})}"

        if action.record:
            return (
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<Response>"
                f"{play_or_say}"
                f'<Record action="{escape(action_url)}" method="POST" maxLength="45" playBeep="true" trim="trim-silence" />'
                f'<Redirect method="POST">{escape(action_url)}</Redirect>'
                "</Response>"
            )

        if action.collect_digits:
            return (
                '<?xml version="1.0" encoding="UTF-8"?>'
                "<Response>"
                f'<Gather action="{escape(action_url)}" method="POST" input="dtmf" numDigits="{action.max_digits}" timeout="8">'
                f"{play_or_say}"
                "</Gather>"
                f'<Redirect method="POST">{escape(action_url)}</Redirect>'
                "</Response>"
            )

        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            f"{play_or_say}"
            f'<Redirect method="POST">{escape(action_url)}</Redirect>'
            "</Response>"
        )

    def _play_or_say(self, audio_url: str | None, escaped_prompt: str, public_base_url: str) -> str:
        if audio_url:
            source = audio_url if audio_url.startswith("http") else f"{public_base_url.rstrip('/')}{audio_url}"
            if source.strip():
                return f"<Play>{escape(source)}</Play>"
        prompt = escaped_prompt.strip() or "Welcome to KrishiMitra. Please wait while we connect the service."
        return f"<Say>{prompt}</Say>"
