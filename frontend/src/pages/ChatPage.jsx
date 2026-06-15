import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { ClipboardList, Landmark, Leaf, Loader2, Mic, Plus, Send, Sparkles, Square, Volume2, X } from "lucide-react";
import { api } from "../api/client";
import { ErrorAlert } from "../components/Ui";
import { useAuth } from "../context/AuthContext";

const languages = [
  { value: "ta", label: "Tamil" },
  { value: "kn", label: "Kannada" },
  { value: "en", label: "English" },
];

const voiceLanguages = {
  ta: "ta-IN",
  kn: "kn-IN",
  en: "en-IN",
};

const addOptions = [
  { label: "Crop disease", prompt: "My crop has yellow leaves and spots. What should I check first?", icon: Leaf },
  { label: "Scheme query", prompt: "Check which government schemes I may be eligible for.", icon: Landmark },
  { label: "Grievance help", prompt: "Help me write and track an agriculture department grievance.", icon: ClipboardList },
];

export default function ChatPage() {
  const { user } = useAuth();
  const location = useLocation();
  const [messages, setMessages] = useState([]);
  const [message, setMessage] = useState(location.state?.prompt || "");
  const [sessionId, setSessionId] = useState(null);
  const [language, setLanguage] = useState(user?.preferred_language || "en");
  const [addOpen, setAddOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [voiceState, setVoiceState] = useState("idle");
  const [error, setError] = useState("");
  const inputRef = useRef(null);
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const audioRef = useRef(null);

  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  function voiceStatusLabel() {
    const labels = {
      listening: "Listening... tap again to stop",
      transcribing: "Converting voice to formatted text...",
      thinking: "Starting AI response...",
      speaking: "Speaking response...",
    };
    return labels[voiceState] || "";
  }

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

  function browserSpeak(text) {
    if (!window.speechSynthesis || !text) return false;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = voiceLanguages[language] || "en-IN";
    utterance.rate = 0.95;
    utterance.onend = () => {
      setVoiceState("idle");
    };
    utterance.onerror = () => setVoiceState("idle");
    window.speechSynthesis.speak(utterance);
    return true;
  }

  async function playBlob(blob) {
    const audioUrl = URL.createObjectURL(blob);
    setVoiceState("speaking");
    try {
      window.speechSynthesis?.cancel();
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.src = audioUrl;
        audioRef.current.onended = () => {
          URL.revokeObjectURL(audioUrl);
          setVoiceState("idle");
        };
        await audioRef.current.play();
      }
    } catch (err) {
      URL.revokeObjectURL(audioUrl);
      setError(err.message);
      setVoiceState("idle");
    }
  }

  function choosePrompt(prompt) {
    setMessage(prompt);
    setAddOpen(false);
    inputRef.current?.focus();
  }

  async function playResponse(text) {
    setVoiceState("speaking");
    setError("");
    try {
      const speechText = text.length > 4800 ? text.slice(0, 4800) : text;
      const blob = await api.speak({ text: speechText, language: voiceLanguages[language] || "en-IN" });
      await playBlob(blob);
    } catch (err) {
      if (!browserSpeak(text)) {
        setError(err.message);
        setVoiceState("idle");
      }
    }
  }

  async function sendQuery(userText, speakResponse = false) {
    if (!userText.trim() || loading) return;
    setAddOpen(false);
    setError("");
    setLoading(true);
    setMessages((items) => [...items, { role: "user", content: userText }]);

    try {
      const response = await api.chat({ message: userText, language, session_id: sessionId });
      setSessionId(response.session_id);
      setMessages((items) => [...items, { role: "assistant", content: response.response, intent: response.intent }]);
      if (speakResponse) {
        await playResponse(response.response);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      if (!speakResponse && voiceState !== "listening") setVoiceState("idle");
    }
  }

  async function sendMessage(event) {
    event.preventDefault();
    const userText = message.trim();
    setMessage("");
    await sendQuery(userText);
  }

  async function sendVoiceConversation(blob) {
    setVoiceState("transcribing");
    setError("");
    try {
      const transcribeData = new FormData();
      transcribeData.append("audio", blob, "voice.webm");
      transcribeData.append("language", voiceLanguages[language] || "en-IN");
      const transcription = await api.transcribeVoice(transcribeData);
      const formattedTranscript = transcription.transcript;
      setMessages((items) => [...items, { role: "user", content: formattedTranscript }]);

      setVoiceState("thinking");
      const respondData = new FormData();
      respondData.append("text", formattedTranscript);
      respondData.append("language", language);
      if (sessionId) respondData.append("session_id", sessionId);
      const answer = await api.voiceRespond(respondData);
      setSessionId(answer.session_id);
      setMessages((items) => [...items, { role: "assistant", content: answer.response, intent: answer.intent }]);

      if (answer.audio_base64) {
        await playBlob(base64ToBlob(answer.audio_base64, answer.audio_mime_type || "audio/wav"));
      } else if (!browserSpeak(answer.response)) {
        setError("Voice response was generated, but audio playback is unavailable.");
        setVoiceState("idle");
      }
    } catch (err) {
      setError(err.message);
      setVoiceState("idle");
    }
  }

  async function startVoice() {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("Voice recording is not supported in this browser.");
      return;
    }
    setError("");
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const mimeType = getRecorderMimeType();
    const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
    chunksRef.current = [];
    streamRef.current = stream;
    recorderRef.current = recorder;

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
      stream.getTracks().forEach((track) => track.stop());
      if (blob.size < 1000) {
        setError("Recording was too short. Hold the mic and speak for a moment.");
        setVoiceState("idle");
        return;
      }
      sendVoiceConversation(blob);
    };

    recorder.start();
    setVoiceState("listening");
  }

  function stopVoice() {
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }

  function toggleVoice() {
    if (voiceState === "listening") {
      stopVoice();
      return;
    }
    if (voiceState === "idle") {
      audioRef.current?.pause();
      window.speechSynthesis?.cancel();
      startVoice().catch((err) => {
        setError(err.message);
        setVoiceState("idle");
      });
    }
  }

  return (
    <div className="assistant-simple">
      <section className="assistant-main simple" aria-label="AI farming assistant">
        <header className="assistant-header">
          <div>
            <span>KrishiMitra</span>
            <h2>AI Assistant</h2>
          </div>
          <div className="assistant-controls">
            <label className="sr-only" htmlFor="chat-language">Response language</label>
            <select id="chat-language" value={language} onChange={(event) => setLanguage(event.target.value)}>
              {languages.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
            </select>
          </div>
        </header>

        <ErrorAlert error={error} />

        <div className="chat-window unified simple">
          {messages.length === 0 && (
            <div className="assistant-empty compact">
              <Sparkles size={22} />
              <h3>Ask one farming question</h3>
              <p>Crop disease, schemes, weather advice, and grievance help all start here.</p>
            </div>
          )}

          {messages.map((item, index) => (
            <div className={`chat-bubble ${item.role}`} key={`${item.role}-${index}`}>
              <span>{item.role === "user" ? "You" : "KrishiMitra"}</span>
              <p>{item.content}</p>
              {item.role === "assistant" && (
                <button className="speak-inline" type="button" onClick={() => playResponse(item.content)} aria-label="Play response">
                  <Volume2 size={15} />
                </button>
              )}
            </div>
          ))}

          {loading && (
            <div className="chat-bubble assistant">
              <span>KrishiMitra</span>
              <p>Thinking...</p>
            </div>
          )}
        </div>

        <form className="chat-input unified query-only" onSubmit={sendMessage}>
          <div className="add-menu-wrap">
            <button className="icon-button" type="button" onClick={() => setAddOpen((open) => !open)} aria-label="Add query type">
              {addOpen ? <X size={18} /> : <Plus size={18} />}
            </button>
            {addOpen && (
              <div className="add-menu">
                {addOptions.map(({ label, prompt, icon: Icon }) => (
                  <button type="button" onClick={() => choosePrompt(prompt)} key={label}>
                    <Icon size={16} />
                    <span>{label}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <input
            ref={inputRef}
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="Query KrishiMitra AI"
          />
          <button className={`voice-orb ${voiceState}`} type="button" onClick={toggleVoice} disabled={!["idle", "listening"].includes(voiceState)} aria-label="Voice query">
            {voiceState === "listening" ? <Square size={18} /> : <Mic size={20} />}
          </button>
          <button className="primary-button send-button" disabled={loading || !message.trim()}>
            {loading ? <Loader2 className="spin-icon" size={16} /> : <Send size={16} />}
            Send
          </button>
        </form>
        <div className="voice-status" aria-live="polite">{voiceStatusLabel()}</div>
        <audio ref={audioRef} className="sr-only" autoPlay playsInline />
      </section>
    </div>
  );
}
