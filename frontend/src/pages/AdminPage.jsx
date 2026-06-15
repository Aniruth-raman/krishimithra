import { useEffect, useState } from "react";
import { api } from "../api/client";
import { EmptyState, ErrorAlert, StatCard, SuccessAlert } from "../components/Ui";

export default function AdminPage() {
  const [analytics, setAnalytics] = useState(null);
  const [users, setUsers] = useState([]);
  const [schemes, setSchemes] = useState([]);
  const [schemeForm, setSchemeForm] = useState({ name: "", description: "", benefits: "", application_process: "", required_documents: "" });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function load() {
    try {
      const [analyticsData, userData, schemeData] = await Promise.all([api.adminAnalytics(), api.adminUsers(), api.adminSchemes()]);
      setAnalytics(analyticsData);
      setUsers(userData.data || []);
      setSchemes(schemeData || []);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    let active = true;
    Promise.all([api.adminAnalytics(), api.adminUsers(), api.adminSchemes()])
      .then(([analyticsData, userData, schemeData]) => {
        if (!active) return;
        setAnalytics(analyticsData);
        setUsers(userData.data || []);
        setSchemes(schemeData || []);
      })
      .catch((err) => {
        if (active) setError(err.message);
      });

    return () => {
      active = false;
    };
  }, []);

  async function toggleUser(id) {
    setError("");
    setSuccess("");
    try {
      await api.toggleUser(id);
      setSuccess("User status updated.");
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function changeRole(id, role) {
    setError("");
    setSuccess("");
    try {
      await api.updateUserRole(id, role);
      setSuccess("User role updated.");
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function createScheme(event) {
    event.preventDefault();
    setError("");
    setSuccess("");
    try {
      await api.createAdminScheme({
        ...schemeForm,
        required_documents: schemeForm.required_documents.split(",").map((item) => item.trim()).filter(Boolean),
        eligibility_criteria: {},
        is_active: true,
      });
      setSuccess("Scheme created.");
      setSchemeForm({ name: "", description: "", benefits: "", application_process: "", required_documents: "" });
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="page">
      <header className="page-header simple-header"><span className="eyebrow">Admin</span><h2>Control center</h2><p>Manage only what needs admin action.</p></header>
      <ErrorAlert error={error} />
      <SuccessAlert message={success} />
      <section className="stats-grid">
        <StatCard label="Total farmers" value={analytics?.users?.farmers} />
        <StatCard label="Active users" value={analytics?.users?.total} tone="blue" />
        <StatCard label="Grievances" value={analytics?.grievances?.total} tone="orange" />
        <StatCard label="Disease reports" value={analytics?.disease_reports?.total} tone="red" />
        <StatCard label="Scheme checks" value={analytics?.schemes?.total_checks} tone="blue" />
      </section>
      <section className="panel">
        <h3>User Management</h3>
        {users.length === 0 ? <EmptyState title="No users" message="Registered users will appear here." /> : <div className="table-wrap"><table><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead><tbody>{users.map((user) => <tr key={user.id}><td>{user.full_name}</td><td>{user.email}</td><td><select value={user.role} onChange={(e) => changeRole(user.id, e.target.value)}><option value="farmer">Farmer</option><option value="officer">Officer</option><option value="admin">Admin</option></select></td><td>{user.is_active ? "Active" : "Inactive"}</td><td><button className="secondary-button" onClick={() => toggleUser(user.id)}>{user.is_active ? "Deactivate" : "Activate"}</button></td></tr>)}</tbody></table></div>}
      </section>
      <div className="two-column">
        <section className="panel">
          <h3>Scheme Management</h3>
          <form className="form-stack" onSubmit={createScheme}>
            <label>Name<input required value={schemeForm.name} onChange={(e) => setSchemeForm({ ...schemeForm, name: e.target.value })} /></label>
            <label>Description<textarea rows="3" value={schemeForm.description} onChange={(e) => setSchemeForm({ ...schemeForm, description: e.target.value })} /></label>
            <label>Benefits<textarea rows="3" value={schemeForm.benefits} onChange={(e) => setSchemeForm({ ...schemeForm, benefits: e.target.value })} /></label>
            <label>Documents comma separated<input value={schemeForm.required_documents} onChange={(e) => setSchemeForm({ ...schemeForm, required_documents: e.target.value })} /></label>
            <label>Application process<textarea rows="3" value={schemeForm.application_process} onChange={(e) => setSchemeForm({ ...schemeForm, application_process: e.target.value })} /></label>
            <button className="primary-button">Create scheme</button>
          </form>
        </section>
        <section className="panel">
          <h3>Active schemes</h3>
          {schemes.length === 0 ? <EmptyState title="No schemes" message="Create schemes to list them here." /> : <div className="scheme-list">{schemes.map((scheme) => <article key={scheme.id}><strong>{scheme.name}</strong><p>{scheme.description}</p><span>{scheme.is_active ? "Active" : "Inactive"}</span></article>)}</div>}
        </section>
      </div>
      <div className="two-column">
        <section className="panel">
          <h3>IVR Monitoring</h3>
          <p>Use the IVR simulator to demo feature-phone farmer support and monitor voice flows.</p>
        </section>
        <section className="panel">
          <h3>Analytics</h3>
          <div className="simple-card-list">
            <article className="info-card"><span>Farmers</span><strong>{analytics?.users?.farmers ?? 0}</strong></article>
            <article className="info-card"><span>Officers</span><strong>{analytics?.users?.officers ?? 0}</strong></article>
            <article className="info-card"><span>Eligible checks</span><strong>{analytics?.schemes?.eligible ?? 0}</strong></article>
          </div>
        </section>
      </div>
    </div>
  );
}
