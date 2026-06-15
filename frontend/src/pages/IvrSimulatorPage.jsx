import { useState } from "react";
import { Bot, Mic, PhoneCall, Play, Square } from "lucide-react";
import { api } from "../api/client";
import { ErrorAlert } from "../components/Ui";

export default function IvrSimulatorPage() {
  const [state, setState] = useState("Incoming Call");
  const [transcript, setTranscript] = useState("My subsidy payment is delayed.");
  const [response, setResponse] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function runDemo() {
    setLoading(true);
    setError("");
    setState("Conversation");
    try {
      const answer = await api.chat({ message: transcript, language: "en" });
      setResponse(answer.response);
      setState("AI Response");
    } catch (err) {
      setError(err.message);
      setState("Incoming Call");
    } finally {
      setLoading(false);
    }
  }

  function resetCall() {
    setState("Incoming Call");
    setResponse("");
  }

  return (
    <div className="page mobile-flow-page ivr-simple-page">
      <header className="page-header simple-header">
        <span className="eyebrow">IVR Simulator</span>
        <h2>Phone call demo</h2>
      </header>
      <ErrorAlert error={error} />
      <section className="ivr-demo-shell">
        <div className="phone-simulation-card">
          <PhoneCall size={42} />
          <span>{state}</span>
          <strong>+91 98765 43210</strong>
          <div className="waveform"><i /><i /><i /><i /><i /></div>
          <div className="action-row">
            <button className="primary-button" type="button" onClick={runDemo} disabled={loading}><Play size={16} /> Run</button>
            <button className="secondary-button" type="button" onClick={resetCall}><Square size={16} /> Reset</button>
          </div>
        </div>
        <div className="panel ivr-conversation-card">
          <h3><Mic size={18} /> Transcript</h3>
          <textarea rows="5" value={transcript} onChange={(event) => setTranscript(event.target.value)} />
          <h3><Bot size={18} /> AI Response</h3>
          <p>{response || "Run the call to show KrishiMitra's answer."}</p>
        </div>
      </section>
    </div>
  );
}
