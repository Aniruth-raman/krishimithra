import { useEffect, useRef, useState } from "react";
import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
import { Loader2, Mic, MicOff, Radio, Square } from "lucide-react";
import { api, getToken } from "../api/client";
import { ErrorAlert } from "../components/Ui";
import { useAuth } from "../context/AuthContext";

const languages = [
  { value: "ta", label: "Tamil" },
  { value: "kn", label: "Kannada" },
  { value: "en", label: "English" },
];

export default function LiveModePage() {
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [language, setLanguage] = useState(user?.preferred_language || "en");
  const [connectionState, setConnectionState] = useState("idle");
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState("");
  const audioRef = useRef(null);
  const clientRef = useRef(null);
  const botAudioStreamRef = useRef(null);
  const liveRef = useRef(false);
  const lastMessageRef = useRef({ role: "", content: "" });

  useEffect(() => () => {
    clientRef.current?.disconnect().catch(() => null);
    botAudioStreamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  function addMessage(role, content) {
    const text = (content || "").trim();
    if (!text) return;
    const normalized = text.replace(/\s+/g, " ").toLowerCase();
    if (lastMessageRef.current.role === role && lastMessageRef.current.content === normalized) return;
    lastMessageRef.current = { role, content: normalized };
    setMessages((items) => {
      const previous = items[items.length - 1];
      if (previous?.role === role && previous.content.replace(/\s+/g, " ").toLowerCase() === normalized) {
        return items;
      }
      return [...items, { role, content: text }];
    });
  }

  function statusText() {
    if (connectionState === "connecting") return "Connecting to KrishiMitra live voice...";
    if (connectionState === "thinking") return "KrishiMitra is thinking...";
    if (connectionState === "speaking") return "KrishiMitra is speaking...";
    if (connectionState === "listening") return muted ? "Live mode is on. Microphone muted." : "Live mode is on. Speak naturally.";
    return "Press Start to begin a hands-free conversation.";
  }

  async function stopLive() {
    liveRef.current = false;
    setConnectionState("idle");
    setMuted(false);
    await clientRef.current?.disconnect().catch(() => null);
    clientRef.current = null;
    botAudioStreamRef.current?.getTracks().forEach((track) => track.stop());
    botAudioStreamRef.current = null;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.srcObject = null;
    }
  }

  async function startLive() {
    setError("");
    setConnectionState("connecting");

    const formData = new FormData();
    formData.append("language", language);
    if (sessionId) formData.append("session_id", sessionId);
    const session = await api.voiceLiveSession(formData);
    const webrtcUrl = session.webrtcUrl || session.connection_url;
    if (!webrtcUrl) throw new Error("Live voice endpoint did not return a WebRTC URL.");

    const token = getToken();
    const endpoint = new URL(webrtcUrl, window.location.origin);
    endpoint.searchParams.set("language", session.language || language);
    endpoint.searchParams.set("session_id", session.session_id);

    const headers = new Headers({ "Content-Type": "application/json" });
    if (token) headers.set("Authorization", `Bearer ${token}`);

    const client = new PipecatClient({
      transport: new SmallWebRTCTransport(),
      enableCam: false,
      enableMic: true,
      callbacks: {
        onConnected: () => {
          liveRef.current = true;
          setConnectionState("listening");
        },
        onDisconnected: () => {
          liveRef.current = false;
          setConnectionState("idle");
          setMuted(false);
        },
        onError: (message) => {
          setError(message?.data?.error || message?.error || "Live voice connection failed.");
          setConnectionState("idle");
        },
        onUserTranscript: (data) => {
          if (data?.final) addMessage("user", data.text);
        },
        onBotOutput: (data) => {
          if (data?.text && data.spoken) addMessage("assistant", data.text);
        },
        onBotTranscript: (data) => {
          if (data?.text) addMessage("assistant", data.text);
        },
        onBotLlmStarted: () => setConnectionState("thinking"),
        onBotTtsStarted: () => setConnectionState("speaking"),
        onBotTtsStopped: () => setConnectionState(liveRef.current ? "listening" : "idle"),
        onTrackStarted: (track, participant) => {
          if (track.kind !== "audio" || participant?.local) return;
          const stream = botAudioStreamRef.current || new MediaStream();
          botAudioStreamRef.current = stream;
          if (!stream.getTracks().some((item) => item.id === track.id)) stream.addTrack(track);
          if (audioRef.current) {
            audioRef.current.srcObject = stream;
            audioRef.current.play().catch(() => null);
          }
        },
        onTrackStopped: (track) => {
          if (track.kind === "audio") botAudioStreamRef.current?.removeTrack(track);
        },
      },
    });

    clientRef.current = client;
    setSessionId(session.session_id);
    await client.connect({ webrtcRequestParams: { endpoint: endpoint.toString(), headers } });
  }

  async function toggleLive() {
    if (connectionState !== "idle") {
      await stopLive();
      return;
    }
    try {
      await startLive();
    } catch (err) {
      await stopLive();
      setError(err.message);
    }
  }

  function toggleMute() {
    const nextMuted = !muted;
    clientRef.current?.enableMic(!nextMuted);
    setMuted(nextMuted);
  }

  const active = connectionState !== "idle";

  return (
    <div className="assistant-simple live-mode-page">
      <section className="assistant-main simple live-mode-panel" aria-label="Live voice assistant">
        <header className="assistant-header">
          <div>
            <span>KrishiMitra</span>
            <h2>Live Mode</h2>
          </div>
          <div className="assistant-controls">
            <label className="sr-only" htmlFor="live-language">Response language</label>
            <select id="live-language" value={language} onChange={(event) => setLanguage(event.target.value)} disabled={active}>
              {languages.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
            </select>
          </div>
        </header>

        <ErrorAlert error={error} />

        <div className="live-mode-stage">
          <div className={`live-orb ${active ? "active" : ""} ${muted ? "muted" : ""}`}>
            {muted ? <MicOff size={54} /> : <Radio size={58} />}
          </div>
          <h3>{active ? "Conversation in progress" : "Ready for live conversation"}</h3>
          <p>{statusText()}</p>
          <div className="live-mode-actions">
            <button className={`primary-button live-start-button ${active ? "stop" : ""}`} type="button" onClick={toggleLive} disabled={connectionState === "connecting"}>
              {connectionState === "connecting" ? <Loader2 className="spin-icon" size={18} /> : active ? <Square size={18} /> : <Radio size={18} />}
              {connectionState === "connecting" ? "Connecting" : active ? "Stop" : "Start"}
            </button>
            <button className={`secondary-button mute-button ${muted ? "active" : ""}`} type="button" onClick={toggleMute} disabled={!active || connectionState === "connecting"}>
              {muted ? <MicOff size={18} /> : <Mic size={18} />}
              {muted ? "Unmute" : "Mute"}
            </button>
          </div>
        </div>

        <div className="chat-window unified simple live-transcript" aria-live="polite">
          {messages.length === 0 ? (
            <div className="assistant-empty compact">
              <Radio size={22} />
              <h3>No transcript yet</h3>
              <p>Start live mode and speak. Completed turns will appear here.</p>
            </div>
          ) : messages.map((item, index) => (
            <div className={`chat-bubble ${item.role}`} key={`${item.role}-${index}`}>
              <span>{item.role === "user" ? "You" : "KrishiMitra"}</span>
              <p>{item.content}</p>
            </div>
          ))}
        </div>

        <audio ref={audioRef} className="sr-only" autoPlay playsInline />
      </section>
    </div>
  );
}
