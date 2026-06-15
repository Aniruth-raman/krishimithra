from __future__ import annotations

from typing import Any
import io
import wave
import uuid

from loguru import logger

from app.config import settings
from app.services.ai.sarvam_ai_service import chat_with_ai
from app.services.ai.sarvam_service import text_to_speech


LANGUAGE_TO_PIPECAT = {
    "en": "EN_IN",
    "en-IN": "EN_IN",
    "ta": "TA_IN",
    "ta-IN": "TA_IN",
    "kn": "KN_IN",
    "kn-IN": "KN_IN",
    "hi": "HI_IN",
    "hi-IN": "HI_IN",
}

CHAT_LANGUAGE = {
    "en-IN": "en",
    "ta-IN": "ta",
    "kn-IN": "kn",
    "hi-IN": "hi",
}


def _language(language: str) -> Any:
    from pipecat.transcriptions.language import Language

    return getattr(Language, LANGUAGE_TO_PIPECAT.get(language, "EN_IN"), Language.EN_IN)


def _chat_language(language: str) -> str:
    return CHAT_LANGUAGE.get(language, language if language in {"en", "ta", "kn", "hi"} else "en")


def _wav_to_pcm(wav_bytes: bytes) -> tuple[bytes, int, int]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        sample_width = wav_file.getsampwidth()
        if sample_width != 2:
            raise ValueError(f"Expected 16-bit PCM WAV from Sarvam TTS, got sample width {sample_width}")
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        audio = wav_file.readframes(wav_file.getnframes())
    return audio, sample_rate, channels


class SarvamLiveResponder:
    def __init__(self, language: str):
        from pipecat.processors.frame_processor import FrameProcessor

        class _Responder(FrameProcessor):
            def __init__(self, response_language: str):
                super().__init__()
                self._language = _chat_language(response_language)
                self._history: list[dict[str, str]] = []
                self._busy = False
                self._last_transcript = ""

            async def process_frame(self, frame, direction):
                from pipecat.frames.frames import TranscriptionFrame
                from pipecat.processors.frame_processor import FrameDirection

                await super().process_frame(frame, direction)

                if direction != FrameDirection.DOWNSTREAM:
                    await self.push_frame(frame, direction)
                    return

                await self.push_frame(frame, direction)

                if not isinstance(frame, TranscriptionFrame):
                    return

                transcript = (frame.text or "").strip()
                if not transcript:
                    return

                normalized = " ".join(transcript.lower().split())
                if self._busy or normalized == self._last_transcript:
                    return

                self._busy = True
                self._last_transcript = normalized
                try:
                    logger.info(f"Live transcript received for LLM: {transcript}")
                    response = await chat_with_ai(
                        message=transcript,
                        history=self._history,
                        language=self._language,
                        context=None,
                        channel="voice",
                    )
                    response = (response or "").strip()
                    if not response:
                        response = "I could not prepare a response. Please ask again."

                    self._history.extend([
                        {"role": "user", "content": transcript},
                        {"role": "assistant", "content": response},
                    ])
                    self._history = self._history[-12:]
                    logger.info(f"Live LLM response ready: {response[:160]}")
                    await self._speak(response)
                except Exception as error:
                    logger.exception(f"Live Sarvam response failed: {error}")
                    await self._speak("I had trouble answering that. Please try again.")
                finally:
                    self._busy = False

            async def _speak(self, text: str):
                from pipecat.frames.frames import TTSAudioRawFrame, TTSStartedFrame, TTSStoppedFrame, TTSTextFrame
                from pipecat.frames.frames import AggregationType

                audio_bytes = await text_to_speech(text[:900], f"{self._language}-IN" if self._language in {"en", "ta", "kn", "hi"} else "en-IN")
                if not audio_bytes:
                    raise RuntimeError("Sarvam TTS returned no audio bytes")

                pcm_audio, sample_rate, channels = _wav_to_pcm(audio_bytes)
                context_id = str(uuid.uuid4())
                await self.push_frame(TTSStartedFrame(context_id=context_id))
                await self.push_frame(TTSTextFrame(text=text, aggregated_by=AggregationType.SENTENCE, context_id=context_id, raw_text=text))
                await self.push_frame(TTSAudioRawFrame(audio=pcm_audio, sample_rate=sample_rate, num_channels=channels, context_id=context_id))
                await self.push_frame(TTSStoppedFrame(context_id=context_id))

        self.processor = _Responder(language)


async def run_live_bot(webrtc_connection: Any, language: str = "en") -> None:
    if not settings.SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY is required for live Pipecat voice conversations.")

    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.worker import PipelineParams, PipelineWorker
    from pipecat.services.sarvam.stt import SarvamSTTService
    from pipecat.transports.base_transport import TransportParams
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
    from pipecat.workers.runner import WorkerRunner

    pipecat_language = _language(language)
    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_out_10ms_chunks=2,
        ),
    )
    stt = SarvamSTTService(
        api_key=settings.SARVAM_API_KEY,
        sample_rate=settings.VOICE_LIVE_SAMPLE_RATE,
        settings=SarvamSTTService.Settings(
            model=settings.SARVAM_STT_MODEL,
            language=pipecat_language,
            vad_signals=True,
            high_vad_sensitivity=True,
        ),
    )
    responder = SarvamLiveResponder(language).processor
    pipeline = Pipeline([
        transport.input(),
        stt,
        responder,
        transport.output(),
    ])
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
    )
    runner = WorkerRunner(handle_sigint=False)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Live WebRTC client connected")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Live WebRTC client disconnected")
        await runner.cancel()

    @worker.event_handler("on_pipeline_error")
    async def on_pipeline_error(worker, frame):
        logger.error(f"Live Pipecat pipeline failed: {frame}")

    await runner.add_workers(worker)
    await runner.run(auto_end=False)
