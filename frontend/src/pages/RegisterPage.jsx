import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { ErrorAlert } from "../components/Ui";

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    phone: "",
    password: "",
    role: "farmer",
    preferred_language: "ta",
    state: "",
    district: "",
    land_size_acres: "",
    primary_crop: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (step === 1) {
      setStep(2);
      return;
    }
    setLoading(true);
    setError("");
    try {
      await register(form);
      await api.updateProfile({
        state: form.state,
        district: form.district,
        land_size_acres: Number(form.land_size_acres) || null,
        primary_crop: form.primary_crop,
      });
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page compact onboarding-page">
      <section className="auth-panel form-panel wide">
        <span className="eyebrow">Step {step} of 2</span>
        <h2>{step === 1 ? "Create your account" : "Tell us about your farm"}</h2>
        <p className="muted">{step === 1 ? "Basic details for your KrishiMitra account." : "This helps the AI give local, crop-aware answers."}</p>
        <ErrorAlert error={error} />
        <form onSubmit={handleSubmit} className="form-grid">
          {step === 1 ? (
            <>
              <label>Full name<input required value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} /></label>
              <label>Phone<input required value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} /></label>
              <label>Email<input type="email" required value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></label>
              <label>Password<input type="password" minLength="6" required value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label>
              <button className="primary-button full-row"><ArrowRight size={16} /> Continue</button>
            </>
          ) : (
            <>
              <label>State<input required value={form.state} onChange={(event) => setForm({ ...form, state: event.target.value })} /></label>
              <label>District<input required value={form.district} onChange={(event) => setForm({ ...form, district: event.target.value })} /></label>
              <label>Farm size<input value={form.land_size_acres} onChange={(event) => setForm({ ...form, land_size_acres: event.target.value })} placeholder="Acres" /></label>
              <label>Main crop<input required value={form.primary_crop} onChange={(event) => setForm({ ...form, primary_crop: event.target.value })} /></label>
              <label className="full-row">Language<select value={form.preferred_language} onChange={(event) => setForm({ ...form, preferred_language: event.target.value })}><option value="ta">Tamil</option><option value="hi">Hindi</option><option value="kn">Kannada</option><option value="en">English</option></select></label>
              <div className="profile-actions full-row">
                <button className="secondary-button" type="button" onClick={() => setStep(1)}><ArrowLeft size={16} /> Back</button>
                <button className="primary-button" disabled={loading}>{loading ? "Creating..." : "Create account"}</button>
              </div>
            </>
          )}
        </form>
        <p className="muted">Already registered? <Link to="/login">Sign in</Link></p>
      </section>
    </div>
  );
}
