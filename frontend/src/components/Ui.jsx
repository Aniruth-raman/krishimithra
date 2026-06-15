export function EmptyState({ title, message }) {
  return (
    <div className="empty-state">
      <h3>{title}</h3>
      <p>{message}</p>
    </div>
  );
}

export function ErrorAlert({ error }) {
  if (!error) return null;
  return <div className="alert error">{error}</div>;
}

export function SuccessAlert({ message }) {
  if (!message) return null;
  return <div className="alert success">{message}</div>;
}

export function LoadingState({ message = "Loading..." }) {
  return (
    <div className="loading-state">
      <div className="spinner" />
      <span>{message}</span>
    </div>
  );
}

export function StatCard({ label, value, tone = "green" }) {
  return (
    <div className={`stat-card ${tone}`}>
      <span>{label}</span>
      <strong>{value ?? 0}</strong>
    </div>
  );
}
