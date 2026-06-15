import { useEffect, useRef, useState } from "react";
import { Bot, Headphones, Languages, Mic, MessageSquare, Radio, Square, Volume2, Zap } from "lucide-react";
import { api } from "../api/client";
import { ErrorAlert } from "../components/Ui";
import { useAuth } from "../context/AuthContext";

const languages = [
  { value: "ta", label: "Tamil", hint: "தமிழில் பேசுங்கள்" },
  { value: "kn", label: "Kannada", hint: "ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡಿ" },
  { value: "hi", label: "Hindi", hint: "हिंदी में बोलें" },
  { value: "en", label: "English", hint: "Speak naturally" },
];

const speechLanguages = {
  ta: "ta-IN",
  kn: "kn-IN",
  hi: "hi-IN",
  en: "en-IN",
};

const statusCopy = {
  idle: "Ready",
  connecting: "Starting voice session",
  listening: "Listening now",
  thinking: "Understanding and preparing reply",
  speaking: "Speaking back",
};

const demoPrompts = [
  "My paddy leaves are yellow. What should I do?",
  "Which subsidy scheme can I apply for?",
  "Create a grievance for delayed subsidy payment.",
  "Track grievance GRV202679449.",
  "Give weather advice for my crop this week.",
];

export default function LiveVoicePage() {
  const { user } = useAuth();
  const [language, setLanguage] = useState(user?.preferred_language || "en");
  const [status, setStatus] = useState("idle");
  const [liveMode, setLiveMode] = useState(false);
  const [fastMode, setFastMode] = useState(true);
  const [sessionId, setSessionId] = useState("");
  const [provider, setProvider] = useState("");
  const [turns, setTurns] = useState([]);
  const [lastTranscript, setLastTranscript] = useState("");
  const [lastResponse, setLastResponse] = useState("");
  const [error, setError] = useState("");

  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const audioRef = useRef(null);
  const activeRef = useRef(false);
  const fastModeRef = useRef(true);
  const sessionIdRef = useRef("");
  const languageRef = useRef(language);
  const cancelRecordingRef = useRef(false);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const vadFrameRef = useRef(null);
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
      stopRecording(true);
      stopPlayback();
    };
  }, []);

  function getRecorderMimeType() {
    const options = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
    return options.find((type) => MediaRecorder.isTypeSupported?.(type)) || "";
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
    audioRef.current?.pause();
    window.speechSynthesis?.cancel();
  }

  function stopRecording(cancel = false) {
    cancelRecordingRef.current = cancel;
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

  async function startSession() {
    const formData = new FormData();
    formData.append("language", languageRef.current);
    if (sessionIdRef.current) formData.append("session_id", sessionIdRef.current);
    const session = await api.voiceLiveSession(formData);
    sessionIdRef.current = session.session_id;
    setSessionId(session.session_id);
    setProvider(session.provider === "pipecat" ? "Pipecat configured, using Sarvam browser loop" : "Sarvam browser loop");
  }

  async function startListening() {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      throw new Error("Voice recording is not supported in this browser.");
    }

    stopPlayback();
    setError("");
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
    if (answer.audio_base64) {
      const blob = base64ToBlob(answer.audio_base64, answer.audio_mime_type || "audio/wav");
      const played = await playAudioBlob(blob, answer.response);
      if (played) return;
    }

    if (!browserSpeak(answer.response)) {
      setError("Audio playback is unavailable in this browser.");
      scheduleNextListen(300);
    }
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
      setLastTranscript(transcript);
      setLastResponse(response);

      if (transcript) {
        setTurns((items) => [
          { role: "user", content: transcript },
          { role: "assistant", content: response, intent: answer.intent },
          ...items,
        ].slice(0, 10));
      }

      await speakAnswer({ ...answer, response });
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
      await startSession();
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

  async function sendDemoPrompt(prompt) {
    setStatus("thinking");
    setError("");
    stopRecording(true);
    try {
      const formData = new FormData();
      formData.append("text", prompt);
      formData.append("language", language);
      formData.append("fast_response", fastMode ? "true" : "false");
      if (sessionIdRef.current) formData.append("session_id", sessionIdRef.current);
      const answer = await api.voiceRespond(formData);
      sessionIdRef.current = answer.session_id;
      setSessionId(answer.session_id);
      const response = cleanText(answer.response);
      setLastTranscript(prompt);
      setLastResponse(response);
      setTurns((items) => [
        { role: "user", content: prompt },
        { role: "assistant", content: response, intent: answer.intent },
        ...items,
      ].slice(0, 10));
      await speakAnswer({ ...answer, response });
    } catch (err) {
      setError(err.message);
      setStatus("idle");
    }
  }

  const selectedLanguage = languages.find((item) => item.value === language) || languages.at(-1);

  return (
    <div className="live-voice-page">
      <section className="live-voice-hero panel">
        <div>
          <span className="eyebrow">Gemini-style voice demo</span>
          <h2>KrishiMitra Live Voice</h2>
          <p>Speak naturally. The app detects your pause, sends the audio to Sarvam STT and KrishiMitra AI, then speaks the reply back automatically.</p>
        </div>
        <div className="live-provider-card">
          <Radio size={19} />
          <div>
            <strong>{provider || "Sarvam browser loop"}</strong>
            <span>{sessionId ? `Session ${sessionId.slice(0, 8)}` : "New voice session"}</span>
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
            <strong>{liveMode ? selectedLanguage.hint : "Press start and ask one farming question"}</strong>
            <p>{liveMode ? "Pause for one second when you finish. I will answer and resume listening." : "Works for disease, schemes, weather, grievance creation, and grievance tracking."}</p>
          </div>

          <div className="live-control-row">
            <button className={liveMode ? "secondary-button danger-soft" : "primary-button"} type="button" onClick={toggleLive}>
              {liveMode ? <Square size={17} /> : <Headphones size={17} />}
              {liveMode ? "Stop live voice" : "Start live voice"}
            </button>
            <button className="secondary-button" type="button" onClick={() => sendDemoPrompt(demoPrompts[0])} disabled={status === "listening" || status === "thinking"}>
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

          <div className="live-demo-prompts">
            <strong>Quick demo prompts</strong>
            {demoPrompts.map((prompt) => (
              <button type="button" key={prompt} onClick={() => sendDemoPrompt(prompt)} disabled={status === "listening" || status === "thinking"}>
                {prompt}
              </button>
            ))}
          </div>
        </aside>
      </section>

      <section className="live-transcript panel">
        <h3><Bot size={18} /> Conversation memory</h3>
        {turns.length === 0 ? (
          <div className="empty-state">
            <h3>No turns yet</h3>
            <p>Start live voice, speak, pause, and KrishiMitra will reply aloud.</p>
          </div>
        ) : (
          <div className="live-turn-list">
            {turns.map((turn, index) => (
              <article className={`live-turn ${turn.role}`} key={`${turn.role}-${index}-${turn.content.slice(0, 20)}`}>
                <span>{turn.role === "user" ? "Farmer" : `KrishiMitra${turn.intent ? ` · ${turn.intent}` : ""}`}</span>
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
