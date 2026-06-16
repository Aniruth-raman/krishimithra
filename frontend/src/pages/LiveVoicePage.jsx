import { useEffect, useRef, useState } from "react";
import { Bot, Headphones, Languages, Mic, MessageSquare, Radio, Square, Volume2, Zap } from "lucide-react";
import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
import { api } from "../api/client";
import { ErrorAlert } from "../components/Ui";
import { useAuth } from "../context/AuthContext";

const languages = [
  { value: "ta", label: "Tamil", hint: "Tamil voice mode" },
  { value: "kn", label: "Kannada", hint: "Kannada voice mode" },
  { value: "hi", label: "Hindi", hint: "Hindi voice mode" },
  { value: "en", label: "English", hint: "English voice mode" },
];

const speechLanguages = {
  ta: "ta-IN",
  kn: "kn-IN",
  hi: "hi-IN",
  en: "en-IN",
};

const statusCopy = {
  idle: "Tap the mic to start",
  connecting: "Opening the microphone",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
};

export default function LiveVoicePage() {
  const { user } = useAuth();
  const [language, setLanguage] = useState(user?.preferred_language || "en");
  const [status, setStatus] = useState("idle");
  const [liveMode, setLiveMode] = useState(false);
  const [fastMode, setFastMode] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [provider, setProvider] = useState("");
  const [inputMode, setInputMode] = useState("");
  const [turns, setTurns] = useState([]);
  const [lastTranscript, setLastTranscript] = useState("");
  const [lastResponse, setLastResponse] = useState("");
  const [error, setError] = useState("");

  const recorderRef = useRef(null);
  const recognitionRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const audioRef = useRef(null);
  const activeRef = useRef(false);
  const fastModeRef = useRef(false);
  const sessionIdRef = useRef("");
  const languageRef = useRef(language);
  const cancelRecordingRef = useRef(false);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const vadFrameRef = useRef(null);
  const pipecatClientRef = useRef(null);
  const pipecatTurnRef = useRef({ user: "", bot: "" });
  const speechStartedRef = useRef(false);
  const silenceStartedAtRef = useRef(null);
  const recordingStartedAtRef = useRef(0);

  useEffect(() => {
    languageRef.current = language;
  }, [language]);

  useEffect(() => {
    fastModeRef.current = fastMode;
  }, [fastMode]);

  useEffect(() => {
    return () => {
      activeRef.current = false;
      disconnectPipecat();
      stopRecording(true);
      stopPlayback();
    };
  }, []);

  function getRecorderMimeType() {
    const options = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
    return options.find((type) => MediaRecorder.isTypeSupported?.(type)) || "";
  }

  function getSpeechRecognition() {
    return window.SpeechRecognition || window.webkitSpeechRecognition;
  }

  function base64ToBlob(base64, mimeType = "audio/wav") {
    const binary = window.atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return new Blob([bytes], { type: mimeType });
  }

  function cleanText(text) {
    return String(text || "")
      .replace(/\*\*(.*?)\*\*/g, "$1")
      .replace(/\[(.*?)\]\((.*?)\)/g, "$1 ($2)")
      .replace(/#{1,6}\s*/g, "")
      .replace(/\s+\n/g, "\n")
      .trim();
  }

  function cleanupVoiceDetection() {
    if (vadFrameRef.current) {
      window.cancelAnimationFrame(vadFrameRef.current);
      vadFrameRef.current = null;
    }
    audioContextRef.current?.close().catch(() => {});
    audioContextRef.current = null;
    analyserRef.current = null;
    silenceStartedAtRef.current = null;
  }

  function stopPlayback() {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current.srcObject = null;
      audioRef.current.removeAttribute("src");
      audioRef.current.load();
    }
    window.speechSynthesis?.cancel();
  }

  function resetPipecatTurn() {
    pipecatTurnRef.current = { user: "", bot: "" };
  }

  function appendPipecatText(key, text) {
    const cleaned = cleanText(text);
    if (!cleaned) return "";
    const current = pipecatTurnRef.current[key] || "";
    if (current.endsWith(cleaned)) return current;
    const next = cleanText(`${current} ${cleaned}`);
    pipecatTurnRef.current = { ...pipecatTurnRef.current, [key]: next };
    return next;
  }

  function flushPipecatTurn() {
    const transcript = cleanText(pipecatTurnRef.current.user);
    const response = cleanText(pipecatTurnRef.current.bot);
    if (transcript || response) {
      setLastTranscript(transcript || lastTranscript);
      setLastResponse(response || lastResponse);
      if (transcript && response) pushTurn(transcript, response, "live");
    }
    resetPipecatTurn();
  }

  function wireRemoteAudio(track, participant) {
    if (!track || track.kind !== "audio" || participant?.local || !audioRef.current) return;
    audioRef.current.srcObject = new MediaStream([track]);
    audioRef.current.play().catch(() => {
      setError("Tap Start live voice again if browser audio playback is blocked.");
    });
  }

  async function disconnectPipecat() {
    const client = pipecatClientRef.current;
    pipecatClientRef.current = null;
    if (!client) return;
    await client.disconnect().catch(() => undefined);
  }

  function stopRecording(cancel = false) {
    cancelRecordingRef.current = cancel;
    recognitionRef.current?.abort();
    recognitionRef.current = null;
    cleanupVoiceDetection();
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }

  function scheduleNextListen(delayMs = 260) {
    if (!activeRef.current) {
      setStatus("idle");
      return;
    }
    window.setTimeout(() => {
      if (activeRef.current) {
        startListening().catch((err) => {
          setError(err.message);
          setStatus("idle");
          activeRef.current = false;
          setLiveMode(false);
        });
      }
    }, delayMs);
  }

  async function startSession() {
    const formData = new FormData();
    formData.append("language", languageRef.current);
    if (sessionIdRef.current) formData.append("session_id", sessionIdRef.current);
    const session = await api.voiceLiveSession(formData);
    sessionIdRef.current = session.session_id;
    setSessionId(session.session_id);
    setProvider(session.provider === "pipecat" ? "Pipecat SmallWebRTC" : "Sarvam browser loop");
    return session;
  }

  async function startPipecatLive(session) {
    if (!session?.pipecat_url) return false;

    await disconnectPipecat();
    stopRecording(true);
    stopPlayback();
    resetPipecatTurn();
    setInputMode("smallwebrtc");

    const transport = new SmallWebRTCTransport({
      iceServers: session.ice_servers || [{ urls: "stun:stun.l.google.com:19302" }],
    });
    const client = new PipecatClient({
      transport,
      enableCam: false,
      enableMic: true,
      callbacks: {
        onConnected: () => setStatus("listening"),
        onDisconnected: () => {
          if (!activeRef.current) setStatus("idle");
        },
        onTransportStateChanged: (state) => {
          if (["connecting", "initializing", "initialized"].includes(state)) setStatus("connecting");
          if (["connected", "ready"].includes(state)) setStatus("listening");
          if (state === "error") setError("SmallWebRTC connection failed. Check the Pipecat bot URL.");
        },
        onTrackStarted: wireRemoteAudio,
        onUserStartedSpeaking: () => setStatus("listening"),
        onUserStoppedSpeaking: () => setStatus("thinking"),
        onBotStartedSpeaking: () => setStatus("speaking"),
        onBotStoppedSpeaking: () => {
          flushPipecatTurn();
          if (activeRef.current) setStatus("listening");
        },
        onUserTranscript: (data) => {
          const transcript = appendPipecatText("user", data?.text);
          if (transcript) setLastTranscript(transcript);
        },
        onBotOutput: (data) => {
          if (data?.spoken === false) return;
          const response = appendPipecatText("bot", data?.text);
          if (response) setLastResponse(response);
        },
        onBotTranscript: (data) => {
          const response = appendPipecatText("bot", data?.text);
          if (response) setLastResponse(response);
        },
        onError: (message) => {
          setError(message?.data?.error || message?.data?.message || "SmallWebRTC voice session failed.");
        },
      },
    });

    pipecatClientRef.current = client;
    await client.connect({
      webrtcRequestParams: { endpoint: session.webrtc_url || session.pipecat_url },
      iceConfig: { iceServers: session.ice_servers || [{ urls: "stun:stun.l.google.com:19302" }] },
    });
    setStatus("listening");
    return true;
  }

  async function startListening() {
    const SpeechRecognition = getSpeechRecognition();
    if (SpeechRecognition) {
      startSpeechRecognition(SpeechRecognition);
      return;
    }
    await startAudioListening();
  }

  function startSpeechRecognition(SpeechRecognition) {
    stopPlayback();
    setError("");
    setInputMode("speech");
    cancelRecordingRef.current = false;

    const recognition = new SpeechRecognition();
    recognition.lang = speechLanguages[languageRef.current] || "en-IN";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognitionRef.current = recognition;

    let sent = false;

    recognition.onresult = (event) => {
      const transcript = Array.from(event.results || [])
        .map((result) => result?.[0]?.transcript || "")
        .join(" ")
        .trim();
      if (!transcript) return;
      sent = true;
      recognition.stop();
      sendTextTurn(transcript);
    };

    recognition.onerror = (event) => {
      if (cancelRecordingRef.current) return;
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        activeRef.current = false;
        setLiveMode(false);
        setStatus("idle");
        setError("Microphone permission is blocked. Allow microphone access and start again.");
        return;
      }
      if (event.error !== "no-speech") {
        setError("Speech recognition paused. Switching to audio capture.");
        recognitionRef.current = null;
        startAudioListening().catch((err) => {
          setError(err.message);
          setStatus("idle");
        });
      }
    };

    recognition.onend = () => {
      recognitionRef.current = null;
      if (cancelRecordingRef.current) {
        cancelRecordingRef.current = false;
        setStatus("idle");
        return;
      }
      if (!sent && activeRef.current) {
        setStatus("idle");
        scheduleNextListen(260);
      }
    };

    recognition.start();
    setStatus("listening");
  }

  function startVoiceDetection(stream, recorder) {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;

    const audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 1024;
    analyser.smoothingTimeConstant = 0.2;
    source.connect(analyser);
    audioContextRef.current = audioContext;
    analyserRef.current = analyser;

    const data = new Uint8Array(analyser.fftSize);
    const speechThreshold = 13;
    const silenceMs = 800;
    const minSpeechMs = 350;
    const noSpeechTimeoutMs = 11000;
    const maxTurnMs = 18000;

    function checkVoice() {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let index = 0; index < data.length; index += 1) {
        const value = data[index] - 128;
        sum += value * value;
      }

      const volume = Math.sqrt(sum / data.length);
      const now = Date.now();
      const elapsed = now - recordingStartedAtRef.current;

      if (volume > speechThreshold) {
        speechStartedRef.current = true;
        silenceStartedAtRef.current = null;
      } else if (speechStartedRef.current) {
        if (!silenceStartedAtRef.current) silenceStartedAtRef.current = now;
        if (elapsed > minSpeechMs && now - silenceStartedAtRef.current > silenceMs) {
          recorder.stop();
          return;
        }
      } else if (elapsed > noSpeechTimeoutMs) {
        recorder.stop();
        return;
      }

      if (elapsed > maxTurnMs) {
        recorder.stop();
        return;
      }

      vadFrameRef.current = window.requestAnimationFrame(checkVoice);
    }

    vadFrameRef.current = window.requestAnimationFrame(checkVoice);
  }

  async function startAudioListening() {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      throw new Error("Voice recording is not supported in this browser.");
    }

    stopPlayback();
    setError("");
    setInputMode("audio");
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const mimeType = getRecorderMimeType();
    const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);

    chunksRef.current = [];
    speechStartedRef.current = false;
    silenceStartedAtRef.current = null;
    recordingStartedAtRef.current = Date.now();
    cancelRecordingRef.current = false;
    streamRef.current = stream;
    recorderRef.current = recorder;

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };

    recorder.onstop = () => {
      cleanupVoiceDetection();
      stream.getTracks().forEach((track) => track.stop());
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });

      if (cancelRecordingRef.current) {
        cancelRecordingRef.current = false;
        setStatus("idle");
        return;
      }

      if (!speechStartedRef.current || blob.size < 1000) {
        setStatus("idle");
        scheduleNextListen(240);
        return;
      }

      sendVoiceTurn(blob);
    };

    recorder.start(150);
    startVoiceDetection(stream, recorder);
    setStatus("listening");
  }

  function browserSpeak(text) {
    if (!window.speechSynthesis || !text) return false;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(cleanText(text).slice(0, 4200));
    utterance.lang = speechLanguages[languageRef.current] || "en-IN";
    utterance.rate = 1.05;
    utterance.pitch = 1;
    utterance.onend = () => scheduleNextListen(220);
    utterance.onerror = () => scheduleNextListen(220);
    window.speechSynthesis.speak(utterance);
    setStatus("speaking");
    return true;
  }

  async function playAudioBlob(blob, fallbackText) {
    const audioUrl = URL.createObjectURL(blob);
    setStatus("speaking");

    try {
      window.speechSynthesis?.cancel();
      audioRef.current.srcObject = null;
      audioRef.current.src = audioUrl;
      audioRef.current.onended = () => {
        URL.revokeObjectURL(audioUrl);
        scheduleNextListen(220);
      };
      audioRef.current.onerror = () => {
        URL.revokeObjectURL(audioUrl);
        if (!browserSpeak(fallbackText)) scheduleNextListen(220);
      };
      await audioRef.current.play();
      return true;
    } catch {
      URL.revokeObjectURL(audioUrl);
      return browserSpeak(fallbackText);
    }
  }

  async function speakAnswer(answer) {
    const spokenResponse = cleanText(answer.spoken_response || answer.response);
    if (answer.audio_base64) {
      const blob = base64ToBlob(answer.audio_base64, answer.audio_mime_type || "audio/wav");
      const played = await playAudioBlob(blob, spokenResponse);
      if (played) return;
    }

    if (!browserSpeak(spokenResponse)) {
      setError("Audio playback is unavailable in this browser.");
      scheduleNextListen(300);
    }
  }

  function pushTurn(transcript, response, intent) {
    setLastTranscript(transcript);
    setLastResponse(response);
    setTurns((items) => [
      { role: "user", content: transcript },
      { role: "assistant", content: response, intent },
      ...items,
    ].slice(0, 10));
  }

  async function sendVoiceTurn(blob) {
    setStatus("thinking");
    setError("");

    try {
      const formData = new FormData();
      formData.append("audio", blob, "live-voice.webm");
      formData.append("language", languageRef.current);
      formData.append("fast_response", fastModeRef.current ? "true" : "false");
      if (sessionIdRef.current) formData.append("session_id", sessionIdRef.current);

      const answer = await api.voiceConversation(formData);
      sessionIdRef.current = answer.session_id;
      setSessionId(answer.session_id);

      const transcript = cleanText(answer.transcript);
      const response = cleanText(answer.response);
      const spokenResponse = cleanText(answer.spoken_response || response);
      if (transcript) pushTurn(transcript, response, answer.intent);
      await speakAnswer({ ...answer, response, spoken_response: spokenResponse });
    } catch (err) {
      setError(err.message);
      scheduleNextListen(800);
    }
  }

  async function sendTextTurn(prompt) {
    setStatus("thinking");
    setError("");

    try {
      const formData = new FormData();
      formData.append("text", prompt);
      formData.append("language", languageRef.current);
      formData.append("fast_response", fastModeRef.current ? "true" : "false");
      if (sessionIdRef.current) formData.append("session_id", sessionIdRef.current);
      const answer = await api.voiceRespond(formData);
      sessionIdRef.current = answer.session_id;
      setSessionId(answer.session_id);

      const transcript = cleanText(answer.transcript || prompt);
      const response = cleanText(answer.response);
      const spokenResponse = cleanText(answer.spoken_response || response);
      pushTurn(transcript, response, answer.intent);
      await speakAnswer({ ...answer, response, spoken_response: spokenResponse });
    } catch (err) {
      setError(err.message);
      scheduleNextListen(800);
    }
  }

  async function startLive() {
    setStatus("connecting");
    setError("");
    activeRef.current = true;
    setLiveMode(true);

    try {
      const session = await startSession();
      if (await startPipecatLive(session)) return;
      await startListening();
    } catch (err) {
      activeRef.current = false;
      setLiveMode(false);
      setStatus("idle");
      setError(err.message);
    }
  }

  function stopLive() {
    activeRef.current = false;
    setLiveMode(false);
    disconnectPipecat();
    stopRecording(true);
    stopPlayback();
    setStatus("idle");
  }

  async function toggleLive() {
    if (liveMode) {
      stopLive();
      return;
    }
    await startLive();
  }

  async function testSpokenReply() {
    stopRecording(true);
    await sendTextTurn("Give a short crop advisory for today's field work.");
  }

  const inputModeLabel = {
    smallwebrtc: "SmallWebRTC live",
    speech: "Browser speech",
    audio: "Audio upload",
  }[inputMode];
  const selectedLanguage = languages.find((item) => item.value === language) || languages.at(-1);

  return (
    <div className="live-voice-page">
      <section className="live-voice-hero panel">
        <div>
          <span className="eyebrow">Live voice</span>
          <h2>Talk to KrishiMitra</h2>
          <p>Ask about crop disease, schemes, weather, or grievances. KrishiMitra listens, answers aloud, and keeps the conversation moving.</p>
        </div>
        <div className="live-provider-card">
          <Radio size={19} />
          <div>
            <strong>{provider || "Sarvam browser loop"}</strong>
            <span>{inputModeLabel ? `${inputModeLabel} mode` : sessionId ? `Session ${sessionId.slice(0, 8)}` : "Ready"}</span>
          </div>
        </div>
      </section>

      <ErrorAlert error={error} />

      <section className="live-voice-grid">
        <div className="live-voice-stage panel">
          <div className="live-stage-top">
            <label>
              <Languages size={16} />
              Response language
              <select value={language} onChange={(event) => setLanguage(event.target.value)} disabled={liveMode && status !== "idle"}>
                {languages.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
              </select>
            </label>
            <label className="voice-mode-toggle">
              <Zap size={16} />
              Reply speed
              <select value={fastMode ? "fast" : "sarvam"} onChange={(event) => setFastMode(event.target.value === "fast")}>
                <option value="fast">Fast browser speech</option>
                <option value="sarvam">Sarvam TTS voice</option>
              </select>
            </label>
          </div>

          <button className={`live-mic-orb ${status} ${liveMode ? "active" : ""}`} type="button" onClick={toggleLive}>
            {liveMode ? <Square size={42} /> : <Mic size={46} />}
          </button>

          <div className="live-state-copy" aria-live="polite">
            <span>{statusCopy[status]}</span>
            <strong>{liveMode ? selectedLanguage.hint : "Start a hands-free conversation"}</strong>
            <p>{liveMode ? "Speak one thought, pause, and the next turn begins after the reply." : "The fastest path uses browser speech recognition, with audio upload as fallback."}</p>
          </div>

          <div className="live-control-row">
            <button className={liveMode ? "secondary-button danger-soft" : "primary-button"} type="button" onClick={toggleLive}>
              {liveMode ? <Square size={17} /> : <Headphones size={17} />}
              {liveMode ? "End live voice" : "Start live voice"}
            </button>
            <button className="secondary-button" type="button" onClick={testSpokenReply} disabled={status === "listening" || status === "thinking"}>
              <Volume2 size={17} />
              Test spoken reply
            </button>
          </div>
        </div>

        <aside className="live-voice-side panel">
          <h3><MessageSquare size={18} /> Current turn</h3>
          <article className="live-current-card">
            <span>You said</span>
            <p>{lastTranscript || "No speech captured yet."}</p>
          </article>
          <article className="live-current-card assistant">
            <span>KrishiMitra replied</span>
            <p>{lastResponse || "The spoken answer will appear here."}</p>
          </article>
        </aside>
      </section>

      <section className="live-transcript panel">
        <h3><Bot size={18} /> Conversation memory</h3>
        {turns.length === 0 ? (
          <div className="empty-state">
            <h3>No turns yet</h3>
            <p>Your spoken turns will appear here after the first reply.</p>
          </div>
        ) : (
          <div className="live-turn-list">
            {turns.map((turn, index) => (
              <article className={`live-turn ${turn.role}`} key={`${turn.role}-${index}-${turn.content.slice(0, 20)}`}>
                <span>{turn.role === "user" ? "Farmer" : `KrishiMitra${turn.intent ? ` - ${turn.intent}` : ""}`}</span>
                <p>{turn.content}</p>
              </article>
            ))}
          </div>
        )}
      </section>

      <audio ref={audioRef} className="sr-only" />
    </div>
  );
}
