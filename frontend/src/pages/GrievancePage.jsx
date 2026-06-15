import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { api } from "../api/client";
import { EmptyState, ErrorAlert, SuccessAlert } from "../components/Ui";

const categories = ["Subsidy Delay", "Crop Loss", "Insurance", "Irrigation", "Market Rate Issue"];

export default function GrievancePage() {
  const [form, setForm] = useState({ category: categories[0], title: "", description: "", district: "" });
  const [trackingId, setTrackingId] = useState("");
  const [tracked, setTracked] = useState(null);
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    api.myGrievances().then(setItems).catch(() => null);
  }, []);

  async function submit(event) {
    event.preventDefault();
    setError("");
    setSuccess("");
    try {
      const payload = { ...form, title: form.title || form.description.slice(0, 80) || form.category };
      const response = await api.createGrievance(payload);
      setItems((current) => [response, ...current]);
      setSuccess(`Tracking ID: ${response.tracking_id}`);
      setForm({ category: categories[0], title: "", description: "", district: "" });
    } catch (err) {
      setError(err.message);
    }
  }

  async function track(event) {
    event.preventDefault();
    setError("");
    setTracked(null);
    try {
      setTracked(await api.trackGrievance(trackingId));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="page mobile-flow-page">
      <header className="page-header simple-header">
        <span className="eyebrow">Grievances</span>
        <h2>Create and track support requests</h2>
      </header>
      <ErrorAlert error={error} />
      <SuccessAlert message={success} />
      <section className="scan-layout">
        <section className="panel">
          <h3>Create new grievance</h3>
          <form className="form-stack" onSubmit={submit}>
            <label>Category<select value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })}>{categories.map((item) => <option key={item}>{item}</option>)}</select></label>
            <label>Description<textarea required rows="5" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} placeholder="Tell us what happened" /></label>
            <label>District<input value={form.district} onChange={(event) => setForm({ ...form, district: event.target.value })} /></label>
            <button className="primary-button">Create grievance</button>
          </form>
        </section>

        <section className="panel">
          <h3>Track grievance</h3>
          <form className="form-stack" onSubmit={track}>
            <label>Tracking ID<input value={trackingId} onChange={(event) => setTrackingId(event.target.value)} placeholder="GRV2026xxxxx" required /></label>
            <button className="secondary-button">Track status</button>
          </form>
          {tracked && <article className="grievance-card featured"><strong>{tracked.tracking_id}</strong><span>{tracked.status}</span><p>{tracked.title}</p><p>{tracked.resolution_notes || "No notes yet"}</p></article>}
        </section>
      </section>

      <section className="panel">
        <h3>My grievances</h3>
        {items.length === 0 ? <EmptyState title="No grievances" message="Submitted grievances will appear here." /> : (
          <div className="simple-card-list">
            {items.map((item) => (
              <article className="grievance-card" key={item.id}>
                <ShieldCheck size={20} />
                <strong>{item.tracking_id}</strong>
                <span>{item.status}</span>
                <p>{item.title}</p>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
