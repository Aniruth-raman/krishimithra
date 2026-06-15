import { Link, useLocation, useNavigate } from "react-router-dom";
import { useState } from "react";
import { Bot, CloudSun, Leaf, MessageSquare, Mic, ShieldCheck } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { ErrorAlert } from "../components/Ui";
import { useTheme } from "../context/ThemeContext";

export default function LoginPage() {
  const { login } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      await login(form);
      navigate(location.state?.from?.pathname || "/");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="landing-shell">
      <header className="landing-nav">
        <div className="brand compact-brand">
          <div className="brand-mark">KM</div>
          <div>
            <h1>KrishiMitra</h1>
            <p>AI farming companion</p>
          </div>
        </div>
        <button className="theme-toggle compact" type="button" onClick={toggleTheme}>
          {theme === "dark" ? "Light" : "Dark"}
        </button>
      </header>

      <main className="landing-grid">
        <section className="landing-copy">
          <span className="eyebrow">Farmer-first AI assistance</span>
          <h1>Ask, speak, scan, and decide with one simple farming companion.</h1>
          <p>KrishiMitra keeps crop help, weather advice, schemes, and grievance support inside two easy assistants built for mobile use.</p>
          <div className="landing-pill-row">
            <span><Bot size={15} /> AI Assistant</span>
            <span><Mic size={15} /> Voice Assistant</span>
            <span><ShieldCheck size={15} /> Farmer-safe guidance</span>
          </div>
          <div className="product-preview" aria-label="KrishiMitra product preview">
            <div className="preview-sidebar">
              <span />
            </div>
            <div className="preview-chat">
              <div className="preview-message user">Can I spray pesticide today?</div>
              <div className="preview-message ai">
                <CloudSun size={16} />
                Delay spraying. Rain risk is elevated and wind drift may reduce effectiveness.
              </div>
              <div className="preview-message ai">
                <Leaf size={16} />
                You can also upload a crop photo inside the assistant for disease guidance.
              </div>
              <div className="preview-composer"><MessageSquare size={16} /> Ask in your language...</div>
            </div>
          </div>
        </section>

        <section className="auth-panel form-panel landing-auth">
          <div className="hero-icon"><Leaf /></div>
          <h2>Sign in</h2>
          <p className="muted">Use your registered farmer, officer, or admin account.</p>
          <ErrorAlert error={error} />
          <form onSubmit={handleSubmit} className="form-stack">
            <label>Email<input type="email" required value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></label>
            <label>Password<input type="password" required value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label>
            <button className="primary-button" disabled={loading}>{loading ? "Signing in..." : "Sign in"}</button>
          </form>
          <p className="muted">New here? <Link to="/register">Create an account</Link></p>
        </section>
      </main>
    </div>
  );
}
