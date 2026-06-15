import { useEffect, useState } from "react";
import { CheckCircle2, FileText } from "lucide-react";
import { api } from "../api/client";
import { EmptyState, ErrorAlert } from "../components/Ui";

export default function SchemePage() {
  const [schemes, setSchemes] = useState([]);
  const [history, setHistory] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ scheme_name: "PM-KISAN", state: "Tamil Nadu", land_ownership: "owned", farmer_category: "small", annual_income: "" });

  useEffect(() => {
    api.schemes().then(setSchemes).catch(() => null);
    api.schemeHistory().then(setHistory).catch(() => null);
  }, []);

  async function check(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const response = await api.checkScheme({ ...form, annual_income: Number(form.annual_income) || null });
      setResult(response);
      setHistory((items) => [response, ...items]);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page mobile-flow-page">
      <header className="page-header simple-header">
        <span className="eyebrow">Schemes</span>
        <h2>Check government schemes</h2>
      </header>
      <ErrorAlert error={error} />
      <section className="scan-layout">
        <form className="panel form-stack" onSubmit={check}>
          <label>Scheme<select value={form.scheme_name} onChange={(event) => setForm({ ...form, scheme_name: event.target.value })}>{schemes.map((scheme) => <option key={scheme.name} value={scheme.name}>{scheme.name}</option>)}</select></label>
          <label>State<input value={form.state} onChange={(event) => setForm({ ...form, state: event.target.value })} /></label>
          <label>Land ownership<input value={form.land_ownership} onChange={(event) => setForm({ ...form, land_ownership: event.target.value })} /></label>
          <label>Annual income<input type="number" value={form.annual_income} onChange={(event) => setForm({ ...form, annual_income: event.target.value })} /></label>
          <button className="primary-button" disabled={loading}>{loading ? "Checking..." : "Check eligibility"}</button>
        </form>
        <section className="panel">
          <h3>Eligibility</h3>
          {!result ? <EmptyState title="No check yet" message="Check a scheme to see eligibility." /> : (
            <div className="scheme-card">
              <CheckCircle2 size={24} />
              <strong>{result.eligibility_status === "requires_verification" ? "Needs verification" : result.is_eligible ? "Eligible" : "Not eligible"}</strong>
              <span>{result.scheme_name}</span>
              <p>{result.eligibility_reason}</p>
              {result.benefits && <p><b>Benefit:</b> {result.benefits}</p>}
              {result.application_steps && <p><b>Apply:</b> {result.application_steps}</p>}
            </div>
          )}
        </section>
      </section>

      <section className="panel">
        <h3>Recent checks</h3>
        {history.length === 0 ? <EmptyState title="No recent checks" message="Your scheme checks will appear here." /> : (
          <div className="simple-card-list">
            {history.slice(0, 4).map((item) => (
              <article className="scheme-card compact" key={item.id}>
                <FileText size={18} />
                <strong>{item.scheme_name}</strong>
                <span>{item.is_eligible === true ? "Eligible" : item.is_eligible === false ? "Not eligible" : "Needs verification"}</span>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
