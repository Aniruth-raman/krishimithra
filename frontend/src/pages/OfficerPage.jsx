import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, ClipboardCheck, Leaf, ShieldCheck } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { EmptyState, ErrorAlert, StatCard, SuccessAlert } from "../components/Ui";

const tabs = [
  { value: "grievances", label: "Grievances" },
  { value: "disease", label: "Disease Reports" },
];

export default function OfficerPage() {
  const [searchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState(searchParams.get("tab") === "disease" ? "disease" : "grievances");
  const [dashboard, setDashboard] = useState(null);
  const [grievances, setGrievances] = useState([]);
  const [reports, setReports] = useState([]);
  const [selected, setSelected] = useState(null);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  const assignedCases = useMemo(() => grievances.filter((item) => item.assigned_officer_id), [grievances]);

  async function load() {
    const [dash, grv, disease] = await Promise.all([api.officerDashboard(), api.officerGrievances(), api.officerDiseaseReports()]);
    setDashboard(dash);
    setGrievances(grv.data || []);
    setReports(disease || []);
    if (!selected && grv.data?.[0]) setSelected(grv.data[0]);
  }

  useEffect(() => {
    let active = true;
    Promise.all([api.officerDashboard(), api.officerGrievances(), api.officerDiseaseReports()])
      .then(([dash, grv, disease]) => {
        if (!active) return;
        setDashboard(dash);
        setGrievances(grv.data || []);
        setReports(disease || []);
        if (grv.data?.[0]) setSelected(grv.data[0]);
      })
      .catch((err) => {
        if (active) setError(err.message);
      });
    return () => {
      active = false;
    };
  }, []);

  async function updateCase(status) {
    if (!selected) return;
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      await api.updateGrievance(selected.id, { status, notes: notes || `Marked ${status}` });
      setSuccess(`Updated ${selected.tracking_id}`);
      setNotes("");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page mobile-flow-page">
      <header className="page-header simple-header">
        <span className="eyebrow">Officer</span>
        <h2>Action items</h2>
      </header>
      <ErrorAlert error={error} />
      <SuccessAlert message={success} />

      <section className="stats-grid action-stats">
        <StatCard label="Open grievances" value={dashboard?.pending_grievances} tone="orange" />
        <StatCard label="Pending disease reports" value={reports.length} tone="red" />
        <StatCard label="Assigned cases" value={assignedCases.length} tone="blue" />
      </section>

      <div className="simple-tabs">
        {tabs.map((tab) => <button className={activeTab === tab.value ? "active" : ""} type="button" onClick={() => setActiveTab(tab.value)} key={tab.value}>{tab.label}</button>)}
      </div>

      {activeTab === "grievances" ? (
        <section className="officer-action-grid">
          <div className="panel">
            <h3>Grievances</h3>
            {grievances.length === 0 ? <EmptyState title="No grievances" message="Cases appear here when farmers submit them." /> : (
              <div className="simple-card-list">
                {grievances.map((item) => (
                  <button className={selected?.id === item.id ? "case-card active" : "case-card"} type="button" onClick={() => setSelected(item)} key={item.id}>
                    <strong>{item.tracking_id}</strong>
                    <span>{item.status} - {item.district || "No district"}</span>
                    <p>{item.title}</p>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="panel">
            <h3>Take action</h3>
            {!selected ? <EmptyState title="Select a case" message="Open a grievance to update it." /> : (
              <div className="action-detail-card">
                <ShieldCheck size={24} />
                <strong>{selected.tracking_id}</strong>
                <span>{selected.category}</span>
                <p>{selected.description || selected.title}</p>
                <label>Notes<textarea rows="4" value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
                <div className="action-row">
                  <button className="secondary-button" disabled={loading} type="button" onClick={() => updateCase("assigned")}><ClipboardCheck size={16} /> Assign</button>
                  <button className="secondary-button" disabled={loading} type="button" onClick={() => updateCase("in_progress")}>Start</button>
                  <button className="primary-button" disabled={loading} type="button" onClick={() => updateCase("closed")}><CheckCircle2 size={16} /> Resolve</button>
                </div>
              </div>
            )}
          </div>
        </section>
      ) : (
        <section className="panel">
          <h3>Disease reports</h3>
          {reports.length === 0 ? <EmptyState title="No reports" message="Disease reports will appear here." /> : (
            <div className="simple-card-list">
              {reports.map((report) => (
                <article className="disease-card compact" key={report.id}>
                  <Leaf size={20} />
                  <strong>{report.disease_name || "Observation"}</strong>
                  <span>{report.crop_type || "Crop"} - {report.severity || "Unknown"}</span>
                  <p>{report.district || "No district"} - {report.farmer || "Farmer"}</p>
                </article>
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
