import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { Camera, ClipboardList, CloudSun, Landmark, Leaf, Loader2, Mic, Paperclip, Plus, ScanLine, Send, Sparkles, Square, Volume2, X } from "lucide-react";
import { api } from "../api/client";
import { ErrorAlert } from "../components/Ui";
import { useAuth } from "../context/AuthContext";

const languages = [
  { value: "ta", label: "Tamil" },
  { value: "hi", label: "Hindi" },
  { value: "kn", label: "Kannada" },
  { value: "en", label: "English" },
];

const voiceLanguages = {
  ta: "ta-IN",
  hi: "hi-IN",
  kn: "kn-IN",
  en: "en-IN",
};

const grievanceCategories = ["Subsidy Delay", "Crop Loss", "Insurance", "Irrigation", "Market Rate Issue"];

const addOptions = [
  { label: "Crop disease help", prompt: "My crop has yellow leaves and spots. What should I check first?", icon: Leaf, type: "prompt" },
  { label: "Weather advice", prompt: "Should I spray pesticide today? Please consider rain, wind, and crop safety.", icon: CloudSun, type: "prompt" },
  { label: "Scheme eligibility", prompt: "Check which government schemes I may be eligible for based on my farm details.", icon: Landmark, type: "prompt" },
  { label: "Create grievance", icon: ClipboardList, type: "grievance" },
];

const suggestedActions = [
  "Why are my leaves yellow?",
  "Should I spray pesticide today?",
  "Which schemes am I eligible for?",
  "Track my grievance",
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
  const [grievanceOpen, setGrievanceOpen] = useState(false);
  const [grievanceLoading, setGrievanceLoading] = useState(false);
  const [grievanceForm, setGrievanceForm] = useState({
    category: grievanceCategories[0],
    title: "",
    description: "",
    district: "",
  });
  const [error, setError] = useState("");
  const inputRef = useRef(null);
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const audioRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const vadFrameRef = useRef(null);
  const speechStartedRef = useRef(false);
  const silenceStartedAtRef = useRef(null);
  const recordingStartedAtRef = useRef(0);
  const cancelRecordingRef = useRef(false);

  useEffect(() => {
    return () => {
      stopVoice(true);
      audioRef.current?.pause();
      window.speechSynthesis?.cancel();
    };
  }, []);

  function voiceStatusLabel() {
    const labels = {
      listening: "Listening... speak and pause",
      transcribing: "Understanding your voice...",
      thinking: "Preparing a quick reply...",
      speaking: "Speaking now...",
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

  function stopRecorderForVad(recorder) {
    if (recorder?.state === "recording") {
      recorder.stop();
    }
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
    const speechThreshold = 14;
    const silenceMs = 650;
    const minSpeechMs = 350;
    const noSpeechTimeoutMs = 9000;

    function checkVoice() {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let index = 0; index < data.length; index += 1) {
        const value = data[index] - 128;
        sum += value * value;
      }
      const volume = Math.sqrt(sum / data.length);
      const now = Date.now();

      if (volume > speechThreshold) {
        speechStartedRef.current = true;
        silenceStartedAtRef.current = null;
      } else if (speechStartedRef.current) {
        if (!silenceStartedAtRef.current) silenceStartedAtRef.current = now;
        const speechDuration = now - recordingStartedAtRef.current;
        const silenceDuration = now - silenceStartedAtRef.current;
        if (speechDuration > minSpeechMs && silenceDuration > silenceMs) {
          stopRecorderForVad(recorder);
          return;
        }
      } else if (now - recordingStartedAtRef.current > noSpeechTimeoutMs) {
        stopRecorderForVad(recorder);
        return;
      }

      vadFrameRef.current = window.requestAnimationFrame(checkVoice);
    }

    vadFrameRef.current = window.requestAnimationFrame(checkVoice);
  }

  function browserSpeak(text) {
    if (!window.speechSynthesis || !text) return false;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = voiceLanguages[language] || "en-IN";
    utterance.rate = 1.03;
    utterance.onend = () => {
      setVoiceState("idle");
    };
    utterance.onerror = () => {
      setVoiceState("idle");
    };
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
        return true;
      }
    } catch {
      URL.revokeObjectURL(audioUrl);
      setVoiceState("idle");
      return false;
    }
    URL.revokeObjectURL(audioUrl);
    setVoiceState("idle");
    return false;
  }

  function inferGrievanceCategory(text) {
    const value = (text || "").toLowerCase();
    if (["insurance", "claim", "premium", "pmfby", "bima"].some((word) => value.includes(word))) return "Insurance";
    if (["crop loss", "damage", "flood", "drought", "destroyed", "loss"].some((word) => value.includes(word))) return "Crop Loss";
    if (["water", "canal", "irrigation", "pump"].some((word) => value.includes(word))) return "Irrigation";
    if (["price", "market", "msp", "rate", "buyer"].some((word) => value.includes(word))) return "Market Rate Issue";
    return "Subsidy Delay";
  }

  function draftGrievanceTitle(text) {
    const cleaned = (text || "").replace(/\s+/g, " ").trim();
    if (!cleaned) return "";
    const firstSentence = cleaned.split(/[.!?]/)[0].trim();
    return (firstSentence || cleaned).slice(0, 90);
  }

  function cleanAssistantText(text) {
    return (text || "")
      .replace(/\*\*(.*?)\*\*/g, "$1")
      .replace(/\[(.*?)\]\((.*?)\)/g, "$1 ($2)")
      .trim();
  }

  function renderMessageContent(content) {
    const lines = String(content || "").split("\n");
    return (
      <div className="message-content">
        {lines.map((line, index) => {
          const trimmed = line.trim();
          if (!trimmed) return null;
          if (trimmed.startsWith("### ")) {
            return <h4 key={`${index}-${trimmed}`}>{cleanAssistantText(trimmed.slice(4))}</h4>;
          }
          if (trimmed.startsWith("## ")) {
            return <h4 key={`${index}-${trimmed}`}>{cleanAssistantText(trimmed.slice(3))}</h4>;
          }
          if (/^[-*]\s+/.test(trimmed)) {
            return <p className="message-bullet" key={`${index}-${trimmed}`}>{cleanAssistantText(trimmed.replace(/^[-*]\s+/, ""))}</p>;
          }
          return <p key={`${index}-${trimmed}`}>{cleanAssistantText(trimmed)}</p>;
        })}
      </div>
    );
  }

  function openGrievanceForm(seedText = "") {
    const cleaned = (seedText || "").trim();
    setGrievanceForm((current) => ({
      ...current,
      category: inferGrievanceCategory(cleaned),
      title: draftGrievanceTitle(cleaned) || current.title,
      description: cleaned || current.description,
    }));
    setGrievanceOpen(true);
    setAddOpen(false);
  }

  function choosePrompt(prompt) {
    setMessage(prompt);
    setAddOpen(false);
    inputRef.current?.focus();
  }

  function chooseAddOption(option) {
    if (option.type === "grievance") {
      openGrievanceForm(message);
      return;
    }
    choosePrompt(option.prompt);
  }

  async function submitGrievance(event) {
    event.preventDefault();
    setError("");
    setGrievanceLoading(true);
    try {
      const response = await api.createGrievance(grievanceForm);
      setMessages((items) => [
        ...items,
        {
          role: "assistant",
          intent: "grievance",
          content: `Grievance report created.\nTracking ID: ${response.tracking_id}\nStatus: ${response.status}\nExpected resolution: ${response.expected_resolution_days} days`,
        },
      ]);
      setGrievanceOpen(false);
      setGrievanceForm({ category: grievanceCategories[0], title: "", description: "", district: "" });
    } catch (err) {
      setError(err.message);
    } finally {
      setGrievanceLoading(false);
    }
  }

  async function playResponse(text) {
    setVoiceState("speaking");
    setError("");
    try {
      const speechText = text.length > 4800 ? text.slice(0, 4800) : text;
      const blob = await api.speak({ text: speechText, language: voiceLanguages[language] || "en-IN" });
      const played = await playBlob(blob);
      if (!played && !browserSpeak(text)) {
        setError("Audio playback is unavailable in this browser.");
        setVoiceState("idle");
      }
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
      setMessages((items) => {
        const nextMessages = [...items, { role: "assistant", content: response.response, intent: response.intent }];
        if (response.intent === "grievance") {
          nextMessages.push({
            role: "assistant",
            content: "Do you want to create an official grievance report from this chat?",
            intent: "grievance",
            action: "create_grievance",
            draft: userText,
          });
        }
        return nextMessages;
      });
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
      const conversationData = new FormData();
      conversationData.append("audio", blob, "voice.webm");
      conversationData.append("language", language);
      conversationData.append("fast_response", "true");
      if (sessionId) conversationData.append("session_id", sessionId);

      setVoiceState("thinking");
      const answer = await api.voiceConversation(conversationData);
      const formattedTranscript = (answer.transcript || "").trim();
      if (!formattedTranscript) {
        const fallbackText = answer.response || "I could not hear that clearly. Please try again.";
        setError(fallbackText);
        const spoke = browserSpeak(fallbackText);
        if (!spoke) {
          setVoiceState("idle");
        }
        return;
      }
      setMessages((items) => [...items, { role: "user", content: formattedTranscript }]);

      setSessionId(answer.session_id);
      setMessages((items) => {
        const nextMessages = [...items, { role: "assistant", content: answer.response, intent: answer.intent }];
        if (answer.intent === "grievance") {
          nextMessages.push({
            role: "assistant",
            content: "Do you want to create an official grievance report from this voice query?",
            intent: "grievance",
            action: "create_grievance",
            draft: formattedTranscript,
          });
        }
        return nextMessages;
      });

      if (answer.audio_base64) {
        const played = await playBlob(base64ToBlob(answer.audio_base64, answer.audio_mime_type || "audio/wav"));
        if (!played && !browserSpeak(answer.response)) {
          setError("Voice response was generated, but audio playback is unavailable.");
          setVoiceState("idle");
        }
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
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
      stream.getTracks().forEach((track) => track.stop());
      if (cancelRecordingRef.current) {
        cancelRecordingRef.current = false;
        setVoiceState("idle");
        return;
      }
      if (!speechStartedRef.current) {
        setVoiceState("idle");
        return;
      }
      if (blob.size < 1000) {
        setVoiceState("idle");
        setError("Recording was too short. Speak for a moment and pause.");
        return;
      }
      sendVoiceConversation(blob);
    };

    recorder.start(150);
    startVoiceDetection(stream, recorder);
    setVoiceState("listening");
  }

  function stopVoice(cancel = false) {
    cancelRecordingRef.current = cancel;
    cleanupVoiceDetection();
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
            <span>AI farming companion</span>
            <h2>Ask KrishiMitra</h2>
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
          <div className="date-separator"><span>Today</span></div>
          {messages.length === 0 && (
            <div className="assistant-empty compact">
              <Sparkles size={22} />
              <h3>What do you need in the field?</h3>
              <p>Ask about crop disease, weather decisions, schemes, or grievances from this one assistant.</p>
              <div className="suggestion-row">
                {suggestedActions.map((action) => (
                  <button type="button" key={action} onClick={() => choosePrompt(action)}>{action}</button>
                ))}
              </div>
            </div>
          )}

          {messages.map((item, index) => (
            <div className={`chat-bubble ${item.role}`} key={`${item.role}-${index}`}>
              <span>{item.role === "user" ? "You" : "KrishiMitra"}</span>
              {renderMessageContent(item.content)}
              {item.action === "create_grievance" && (
                <button className="secondary-button bubble-action" type="button" onClick={() => openGrievanceForm(item.draft)}>
                  Create grievance report
                </button>
              )}
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

        {grievanceOpen && (
          <section className="grievance-composer" aria-label="Create grievance report">
            <div className="grievance-composer-header">
              <div>
                <strong>Create grievance report</strong>
                <span>This creates a real case with a tracking ID.</span>
              </div>
              <button className="icon-button" type="button" onClick={() => setGrievanceOpen(false)} aria-label="Close grievance form">
                <X size={17} />
              </button>
            </div>
            <form className="grievance-form" onSubmit={submitGrievance}>
              <label>
                Category
                <select value={grievanceForm.category} onChange={(event) => setGrievanceForm({ ...grievanceForm, category: event.target.value })}>
                  {grievanceCategories.map((category) => <option key={category}>{category}</option>)}
                </select>
              </label>
              <label>
                District
                <input value={grievanceForm.district} onChange={(event) => setGrievanceForm({ ...grievanceForm, district: event.target.value })} placeholder="Optional" />
              </label>
              <label className="full-row">
                Title
                <input required value={grievanceForm.title} onChange={(event) => setGrievanceForm({ ...grievanceForm, title: event.target.value })} placeholder="Short issue title" />
              </label>
              <label className="full-row">
                Description
                <textarea required rows="4" value={grievanceForm.description} onChange={(event) => setGrievanceForm({ ...grievanceForm, description: event.target.value })} placeholder="Explain what happened, application ID, date, amount, officer/office, and documents if available." />
              </label>
              <div className="grievance-actions full-row">
                <button className="secondary-button" type="button" onClick={() => setGrievanceOpen(false)}>Cancel</button>
                <button className="primary-button" disabled={grievanceLoading || !grievanceForm.title.trim() || !grievanceForm.description.trim()}>
                  {grievanceLoading ? <Loader2 className="spin-icon" size={16} /> : <ClipboardList size={16} />}
                  Submit report
                </button>
              </div>
            </form>
          </section>
        )}

        <form className="chat-input unified query-only" onSubmit={sendMessage}>
          <div className="add-menu-wrap">
            <button className="icon-button" type="button" onClick={() => setAddOpen((open) => !open)} aria-label="Add query type">
              {addOpen ? <X size={18} /> : <Plus size={18} />}
            </button>
            {addOpen && (
              <div className="add-menu">
                {addOptions.map((option) => {
                  const Icon = option.icon;
                  return (
                  <button type="button" onClick={() => chooseAddOption(option)} key={option.label}>
                    <Icon size={16} />
                    <span>{option.label}</span>
                  </button>
                  );
                })}
              </div>
            )}
          </div>
          <input
            ref={inputRef}
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="Ask about crops, weather, schemes, or grievances..."
          />
          <button className="composer-tool" type="button" aria-label="Attach file"><Paperclip size={18} /></button>
          <button className="composer-tool" type="button" aria-label="Upload image"><Camera size={18} /></button>
          <button className="composer-tool" type="button" aria-label="Screen capture"><ScanLine size={18} /></button>
          <button className={`voice-orb ${voiceState}`} type="button" onClick={toggleVoice} disabled={!["idle", "listening"].includes(voiceState)} aria-label="Voice query">
            {voiceState === "listening" ? <Square size={18} /> : <Mic size={20} />}
          </button>
          <button className="primary-button send-button" disabled={loading || !message.trim()}>
            {loading ? <Loader2 className="spin-icon" size={16} /> : <Send size={16} />}
            Send
          </button>
        </form>
        <div className="voice-status" aria-live="polite">{voiceStatusLabel()}</div>
        <audio ref={audioRef} className="sr-only" />
      </section>
    </div>
  );
}
