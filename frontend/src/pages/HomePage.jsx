import { Link, Navigate } from "react-router-dom";
import { Bot, ClipboardList, CloudSun, Landmark, Leaf, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";

const quickPrompts = [
  { text: "My crop leaves have spots. What should I check first?", icon: Leaf },
  { text: "Am I eligible for PM-KISAN?", icon: Landmark },
  { text: "How do I raise a subsidy grievance?", icon: ClipboardList },
];

export default function HomePage() {
  const { user } = useAuth();
  const [weather, setWeather] = useState(null);
  const [hotspots, setHotspots] = useState([]);
  const [weatherError, setWeatherError] = useState("");

  useEffect(() => {
    if (user?.role !== "farmer") return undefined;
    let active = true;
    api.myWeather()
      .then((data) => {
        if (active) setWeather(data);
      })
      .catch((error) => {
        if (active) setWeatherError(error.message);
      });
    api.diseaseHotspots()
      .then((data) => {
        if (active) setHotspots(data.hotspots || []);
      })
      .catch(() => null);
    return () => {
      active = false;
    };
  }, [user?.role]);

  if (user?.role === "officer") return <Navigate to="/officer" replace />;
  if (user?.role === "admin") return <Navigate to="/admin" replace />;

  return (
    <div className="page next-dashboard">
      <header className="page-header dashboard-header">
        <div>
          <span className="eyebrow">Personal AI workspace</span>
          <h2>Good to see you, {user?.full_name}</h2>
          <p>Monitor field context, weather risk, disease activity, and the next best farming actions from one calm workspace.</p>
        </div>
      </header>

      <section className="dashboard-actions">
        <Link className="primary-action" to="/assistant">
          <Bot size={22} />
          <div>
            <strong>Open AI Assistant</strong>
            <span>Ask, compare, cite, draft, and act from one conversation.</span>
          </div>
        </Link>
        <Link className="secondary-action" to="/disease">
          <Leaf size={20} />
          <div>
            <strong>Crop Disease Scan</strong>
            <span>Upload JPG, JPEG, PNG, or WebP crop images with validation.</span>
          </div>
        </Link>
        <Link className="secondary-action" to="/profile">
          <UserRound size={20} />
          <div>
            <strong>Farmer Profile</strong>
            <span>Keep crop, district, land, and language context current.</span>
          </div>
        </Link>
      </section>

      <section className="two-column intelligence-grid">
        <div className="panel live-card">
          <h3><CloudSun size={18} /> Weather Intelligence</h3>
          {weather ? (
            <div className="result-list">
              <strong>{weather.resolved_location}</strong>
              <span>{weather.current?.temperature_c ?? "-"} C - Humidity {weather.current?.humidity_percent ?? "-"}%</span>
              <span>Rain {weather.current?.rainfall_mm ?? 0} mm - Wind {weather.current?.wind_speed_kmh ?? "-"} km/h</span>
              <p><b>Spray:</b> {weather.spray_window?.decision?.replaceAll("_", " ")} - {weather.spray_window?.reason}</p>
              <p><b>Irrigation:</b> {weather.irrigation?.decision?.replaceAll("_", " ")} - {weather.irrigation?.reason}</p>
            </div>
          ) : (
            <p>{weatherError || "Loading weather from your profile district..."}</p>
          )}
        </div>
        <div className="panel live-card">
          <h3><Leaf size={18} /> Disease Hotspots</h3>
          {hotspots.length ? (
            <div className="result-list">
              {hotspots.slice(0, 4).map((item) => (
                <span key={`${item.district}-${item.issue}-${item.severity}`}>
                  {item.district}: {item.issue} - {item.case_count} cases - {item.severity}
                </span>
              ))}
            </div>
          ) : (
            <p>No disease hotspots reported in the last 30 days.</p>
          )}
        </div>
      </section>

      <section className="panel quick-panel">
        <h3>Suggested Next Moves</h3>
        <div className="quick-query-grid">
          {quickPrompts.map(({ text, icon: Icon }) => (
            <Link className="quick-query" to="/assistant" state={{ prompt: text }} key={text}>
              <Icon size={18} />
              <span>{text}</span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
