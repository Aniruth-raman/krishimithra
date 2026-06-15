import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Camera, ImagePlus, MessageCircle } from "lucide-react";
import { api } from "../api/client";
import { EmptyState, ErrorAlert } from "../components/Ui";

export default function DiseasePage() {
  const [cropType, setCropType] = useState("");
  const [image, setImage] = useState(null);
  const [preview, setPreview] = useState("");
  const [result, setResult] = useState(null);
  const [reports, setReports] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.diseaseReports().then(setReports).catch(() => null);
  }, []);

  function chooseImage(file) {
    setImage(file);
    setPreview(file ? URL.createObjectURL(file) : "");
  }

  async function analyze(event) {
    event.preventDefault();
    if (!image) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const formData = new FormData();
      formData.append("image", image);
      if (cropType) formData.append("crop_type", cropType);
      const response = await api.analyzeDisease(formData);
      setResult(response);
      setReports((items) => [response, ...items]);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const issueName = result?.disease_name || result?.pest_name || "Crop issue";

  return (
    <div className="page mobile-flow-page">
      <header className="page-header simple-header">
        <span className="eyebrow">Disease Scan</span>
        <h2>Scan your crop</h2>
      </header>
      <ErrorAlert error={error} />
      <section className="scan-layout">
        <form className="panel scan-card" onSubmit={analyze}>
          <label>Crop name<input value={cropType} onChange={(event) => setCropType(event.target.value)} placeholder="Paddy, tomato, cotton" /></label>
          <label className="upload-dropzone">
            {preview ? <img src={preview} alt="Crop preview" /> : <><Camera size={48} /><strong>Take or upload crop photo</strong><span>JPG, JPEG, PNG, WebP</span></>}
            <input type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" onChange={(event) => chooseImage(event.target.files?.[0])} required />
          </label>
          <button className="primary-button" disabled={loading || !image}>{loading ? "Checking..." : "Analyze crop"}</button>
        </form>

        <section className="panel">
          <h3>Analysis</h3>
          {!result ? <EmptyState title="No scan yet" message="Upload a clear leaf or crop image." /> : (
            <div className="disease-card">
              <ImagePlus size={22} />
              <strong>{issueName}</strong>
              <span>Confidence: {result.confidence_score ?? "N/A"}</span>
              <span>Severity: {result.severity || "Unknown"}</span>
              <p>{result.treatment || result.description}</p>
              <Link className="secondary-button" to="/assistant" state={{ prompt: `Explain ${issueName} in my ${cropType || "crop"} and what I should do next.` }}>
                <MessageCircle size={16} /> Ask AI about this disease
              </Link>
            </div>
          )}
        </section>
      </section>

      <section className="panel">
        <h3>Recent scans</h3>
        {reports.length === 0 ? <EmptyState title="No scans" message="Your crop scans will appear here." /> : (
          <div className="simple-card-list">
            {reports.slice(0, 4).map((report) => (
              <article className="disease-card compact" key={report.id}>
                <strong>{report.disease_name || report.pest_name || "Observation"}</strong>
                <span>{report.crop_type || "Crop"} - {report.severity || "Unknown"}</span>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
