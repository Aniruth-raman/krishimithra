import { useRef, useState } from "react";
import { Bot, CheckCircle2, ClipboardList, CloudSun, FileText, Landmark, Loader2, Mic, PhoneCall, Play, Search, Square, Stethoscope, Volume2 } from "lucide-react";
import { api } from "../api/client";
import { ErrorAlert, SuccessAlert } from "../components/Ui";

const languageOptions = [
  { value: "ta", label: "Tamil", audio: "ta-IN" },
  { value: "kn", label: "Kannada", audio: "kn-IN" },
  { value: "en", label: "English", audio: "en-IN" },
];

const menuItems = [
  {
    id: "disease",
    digit: "1",
    title: "Disease Query",
    icon: Stethoscope,
    sample: "My tomato leaves have yellow spots and are curling. What should I do?",
  },
  {
    id: "scheme",
    digit: "2",
    title: "Scheme Eligibility",
    icon: Landmark,
    sample: "Am I eligible for PM-KISAN if I own two acres of land?",
  },
  {
    id: "grievance",
    digit: "3",
    title: "Grievance",
    icon: ClipboardList,
    sample: "My crop loss subsidy is delayed for two months. Please register a grievance.",
  },
  {
    id: "track",
    digit: "4",
    title: "Track Grievance",
    icon: Search,
    sample: "GRV202679449 track this grievance",
  },
  {
    id: "weather",
    digit: "5",
    title: "Weather Advice",
    icon: CloudSun,
    sample: "Can I spray pesticide today if rain is expected?",
  },
];

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

function cleanResponse(text) {
  return String(text || "")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/#{1,6}\s/g, "")
    .trim();
}

export default function IvrSimulatorPage() {
  const [language, setLanguage] = useState("en");
  const [selectedMenu, setSelectedMenu] = useState(menuItems[0]);
  const [callStatus, setCallStatus] = useState("Idle");
  const [recording, setRecording] = useState(false);
  const [loading, setLoading] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [responseText, setResponseText] = useState("");
  const [manualText, setManualText] = useState(menuItems[0].sample);
  const [toNumber, setToNumber] = useState("");
  const [trackingId, setTrackingId] = useState("GRV202679449");
  const [createdCase, setCreatedCase] = useState(null);
  const [trackedCase, setTrackedCase] = useState(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const audioRef = useRef(null);

  function selectedLanguage() {
    return languageOptions.find((item) => item.value === language) || languageOptions[2];
  }

  function selectMenu(item) {
    setSelectedMenu(item);
    setManualText(item.sample);
    setCreatedCase(null);
    setTrackedCase(null);
    setSuccess("");
    setError("");
  }

  function startCall() {
    setCallStatus("Connected");
    setSuccess("Incoming call connected. IVR simulator is ready.");
    speakBrowser(`Welcome to KrishiMitra call center. Language selected: ${selectedLanguage().label}. Choose a menu option and start recording.`);
  }

  function endCall() {
    stopRecording(true);
    audioRef.current?.pause();
    window.speechSynthesis?.cancel();
    setCallStatus("Ended");
  }

  async function startRealTwilioCall(event) {
    event.preventDefault();
    if (!toNumber.trim()) return;
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      const result = await api.ivrDemoCall(toNumber.trim());
      setCallStatus("Twilio call initiated");
      setSuccess(`Real phone call started. Twilio status: ${result.status || "queued"}. Call SID: ${result.call_sid || "-"}`);
    } catch (err) {
      setError(err.message);
      setCallStatus("Twilio call failed");
    } finally {
      setLoading(false);
    }
  }

  async function startScenarioPhoneCall(scenario) {
    if (!toNumber.trim()) {
      setError("Enter a destination phone number first.");
      return;
    }
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      const result = await api.ivrDemoScenarioCall(toNumber.trim(), scenario);
      setCallStatus(`${scenario} phone demo initiated`);
      setSuccess(`${scenario} phone demo started. Twilio status: ${result.status || "queued"}. Call SID: ${result.call_sid || "-"}`);
    } catch (err) {
      setError(err.message);
      setCallStatus("Scenario call failed");
    } finally {
      setLoading(false);
    }
  }

  function speakBrowser(text) {
    if (!window.speechSynthesis || !text) return false;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(cleanResponse(text));
    utterance.lang = selectedLanguage().audio;
    utterance.rate = 1.02;
    window.speechSynthesis.speak(utterance);
    return true;
  }

  async function playAudioBase64(audioBase64, mimeType = "audio/wav") {
    if (!audioBase64 || !audioRef.current) return false;
    const audioUrl = URL.createObjectURL(base64ToBlob(audioBase64, mimeType));
    try {
      audioRef.current.pause();
      audioRef.current.src = audioUrl;
      audioRef.current.onended = () => URL.revokeObjectURL(audioUrl);
      await audioRef.current.play();
      return true;
    } catch {
      URL.revokeObjectURL(audioUrl);
      return false;
    }
  }

  async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("Browser microphone recording is not supported. Use the typed demo box instead.");
      return;
    }
    setError("");
    setSuccess("");
    setTranscript("");
    setResponseText("");
    setCallStatus("Listening");
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
      stream.getTracks().forEach((track) => track.stop());
      setRecording(false);
      if (chunksRef.current.length) {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        sendVoiceTurn(blob);
      }
    };

    recorder.start(200);
    setRecording(true);
  }

  function stopRecording(cancel = false) {
    if (cancel) chunksRef.current = [];
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    setRecording(false);
  }

  async function sendVoiceTurn(blob) {
    setLoading(true);
    setCallStatus("AI processing");
    setError("");
    try {
      const formData = new FormData();
      formData.append("audio", blob, "ivr-simulator.webm");
      formData.append("language", language);
      const answer = await api.voiceConversation(formData);
      setTranscript(answer.transcript || "");
      setResponseText(answer.response || "");
      setCallStatus("AI responded");
      if (answer.audio_base64) {
        const played = await playAudioBase64(answer.audio_base64, answer.audio_mime_type || "audio/wav");
        if (!played) speakBrowser(answer.response);
      } else {
        speakBrowser(answer.response);
      }
    } catch (err) {
      setError(err.message);
      setCallStatus("Error");
    } finally {
      setLoading(false);
    }
  }

  async function sendTypedTurn(event) {
    event.preventDefault();
    if (!manualText.trim()) return;
    setLoading(true);
    setError("");
    setSuccess("");
    setTranscript(manualText.trim());
    setCallStatus("AI processing");
    try {
      const answer = await api.chat({ message: manualText.trim(), language });
      setResponseText(answer.response);
      setCallStatus("AI responded");
      speakBrowser(answer.response);
    } catch (err) {
      setError(err.message);
      setCallStatus("Error");
    } finally {
      setLoading(false);
    }
  }

  async function createGrievanceFromCall() {
    const description = transcript || manualText || selectedMenu.sample;
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      const caseData = await api.createGrievance({
        category: "Subsidy Delay",
        title: description.slice(0, 90) || "IVR simulator grievance",
        description,
      });
      setCreatedCase(caseData);
      setTrackingId(caseData.tracking_id);
      setSuccess(`Grievance created from IVR simulator. Tracking ID: ${caseData.tracking_id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function trackGrievance(event) {
    event.preventDefault();
    if (!trackingId.trim()) return;
    setLoading(true);
    setError("");
    setTrackedCase(null);
    try {
      const result = await api.trackGrievance(trackingId.trim());
      setTrackedCase(result);
      setResponseText(`Tracking ID: ${result.tracking_id}\nStatus: ${result.status}\nTitle: ${result.title}\nOfficer: ${result.assigned_officer || "Not assigned"}`);
      setCallStatus("Tracking loaded");
      speakBrowser(`Tracking ID ${result.tracking_id}. Current status is ${result.status}.`);
    } catch (err) {
      setError(err.message);
      setCallStatus("Tracking failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page ivr-simulator-page">
      <header className="page-header ivr-hero">
        <div>
          <span className="eyebrow">Demo Mode</span>
          <h2>KrishiMitra Call Center</h2>
          <p>Demonstrate how a feature-phone farmer reaches AI support through voice without depending on live telecom infrastructure.</p>
        </div>
        <div className="fake-call-card">
          <PhoneCall size={28} />
          <div>
            <span>Incoming Call</span>
            <strong>+91 98765 43210</strong>
            <small>{callStatus}</small>
          </div>
        </div>
      </header>

      <ErrorAlert error={error} />
      <SuccessAlert message={success} />

      <section className="ivr-simulator-grid">
        <div className="panel ivr-phone-panel">
          <div className="ivr-phone-screen">
            <div className="ivr-status-row">
              <span>☎ Connected Farmer</span>
              <strong>{selectedLanguage().label}</strong>
            </div>
            <h3>Voice IVR Flow</h3>
            <p>Farmer → Voice → AI → Disease / Scheme / Weather / Grievance → Officer Dashboard</p>
            <div className="ivr-call-actions">
              <button className="primary-button" type="button" onClick={startCall}>
                <PhoneCall size={16} /> Start Call
              </button>
              <button className="secondary-button" type="button" onClick={endCall}>
                <Square size={16} /> End
              </button>
            </div>
          </div>

          <form className="ivr-real-call-card" onSubmit={startRealTwilioCall}>
            <h3>Call Real Phone</h3>
            <p>This uses Twilio keypad and speech recognition. Press 1/2/3/4 or say disease, grievance, scheme, or weather.</p>
            <label>
              Destination number
              <input value={toNumber} onChange={(event) => setToNumber(event.target.value)} placeholder="+91XXXXXXXXXX" />
            </label>
            <button className="primary-button" disabled={loading || !toNumber.trim()}>
              {loading ? <Loader2 className="spin-icon" size={16} /> : <PhoneCall size={16} />}
              Interactive Phone Call
            </button>
            <div className="ivr-scenario-call-grid">
              <button type="button" className="secondary-button" onClick={() => startScenarioPhoneCall("disease")} disabled={loading || !toNumber.trim()}>
                Disease Call
              </button>
              <button type="button" className="secondary-button" onClick={() => startScenarioPhoneCall("grievance")} disabled={loading || !toNumber.trim()}>
                Grievance Call
              </button>
              <button type="button" className="secondary-button" onClick={() => startScenarioPhoneCall("scheme")} disabled={loading || !toNumber.trim()}>
                Scheme Call
              </button>
              <button type="button" className="secondary-button" onClick={() => startScenarioPhoneCall("weather")} disabled={loading || !toNumber.trim()}>
                Weather Call
              </button>
            </div>
          </form>

          <div className="ivr-language-box">
            <h3>Select Language</h3>
            <div className="ivr-radio-row">
              {languageOptions.map((item) => (
                <label className="ivr-radio" key={item.value}>
                  <input type="radio" checked={language === item.value} onChange={() => setLanguage(item.value)} />
                  <span>{item.label}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="ivr-menu-list">
            <h3>Main Menu</h3>
            {menuItems.map((item) => {
              const Icon = item.icon;
              return (
                <button className={`ivr-menu-item ${selectedMenu.id === item.id ? "active" : ""}`} type="button" onClick={() => selectMenu(item)} key={item.id}>
                  <strong>{item.digit}</strong>
                  <Icon size={18} />
                  <span>{item.title}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="panel ivr-workflow-panel">
          <div className="ivr-workflow-header">
            <div>
              <span className="eyebrow">Selected Option {selectedMenu.digit}</span>
              <h3>{selectedMenu.title}</h3>
            </div>
            <Bot size={28} />
          </div>

          <div className="ivr-record-row">
            <button className={`voice-orb ${recording ? "listening" : ""}`} type="button" onClick={recording ? () => stopRecording(false) : startRecording} disabled={loading}>
              {recording ? <Square size={18} /> : <Mic size={20} />}
            </button>
            <div>
              <strong>{recording ? "Recording farmer voice..." : "Start Recording"}</strong>
              <p>Record a farmer query. Sarvam STT converts it, the AI router answers, and TTS speaks back.</p>
            </div>
          </div>

          <form className="ivr-typed-demo" onSubmit={sendTypedTurn}>
            <label>
              Typed fallback for demo
              <textarea rows="3" value={manualText} onChange={(event) => setManualText(event.target.value)} />
            </label>
            <button className="secondary-button" disabled={loading || !manualText.trim()}>
              {loading ? <Loader2 className="spin-icon" size={16} /> : <Play size={16} />}
              Run Typed Call
            </button>
          </form>

          <div className="ivr-results">
            <article>
              <span>Farmer said</span>
              <p>{transcript || "Transcript appears here after recording."}</p>
            </article>
            <article>
              <span>AI response</span>
              <p>{cleanResponse(responseText) || "AI response appears here and can be played aloud."}</p>
              {responseText && (
                <button className="secondary-button" type="button" onClick={() => speakBrowser(responseText)}>
                  <Volume2 size={16} /> Play AI Response
                </button>
              )}
            </article>
          </div>

          {selectedMenu.id === "grievance" && (
            <div className="ivr-case-actions">
              <button className="primary-button" type="button" onClick={createGrievanceFromCall} disabled={loading}>
                {loading ? <Loader2 className="spin-icon" size={16} /> : <ClipboardList size={16} />}
                Create Grievance for Officer Dashboard
              </button>
              {createdCase && (
                <div className="tracking-card">
                  <strong>{createdCase.tracking_id}</strong>
                  <span>{createdCase.status}</span>
                  <p>{createdCase.title}</p>
                </div>
              )}
            </div>
          )}

          <form className="ivr-track-card" onSubmit={trackGrievance}>
            <label>
              Track grievance from call
              <input value={trackingId} onChange={(event) => setTrackingId(event.target.value)} placeholder="GRV2026xxxxx" />
            </label>
            <button className="secondary-button" disabled={loading || !trackingId.trim()}>
              <Search size={16} /> Track
            </button>
          </form>

          {trackedCase && (
            <div className="tracking-card">
              <strong>{trackedCase.tracking_id}</strong>
              <span>{trackedCase.status}</span>
              <h4>{trackedCase.title}</h4>
              <p>{trackedCase.description}</p>
            </div>
          )}
        </div>
      </section>

      <section className="panel ivr-demo-script">
        <h3><FileText size={18} /> Judge Demo Script</h3>
        <p>
          This simulator represents the IVR flow for feature-phone farmers. The backend already has telephony provider abstraction, and the same workflow can be exposed to Twilio or Exotel. For the hackathon demo, this page avoids telecom tunnel failures while still showing voice, AI routing, TTS, grievance creation, and officer dashboard integration.
        </p>
        <div className="ivr-flow-line">
          <span>Farmer</span><span>Voice</span><span>AI</span><span>Service Router</span><span>Officer Dashboard</span>
        </div>
      </section>

      <audio ref={audioRef} className="sr-only" />
    </div>
  );
}
