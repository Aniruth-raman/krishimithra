import { useEffect, useState } from "react";
import { CloudRain, Droplets, Leaf, SunMedium, Wind } from "lucide-react";
import { api } from "../api/client";
import { EmptyState, ErrorAlert } from "../components/Ui";

export default function WeatherPage() {
  const [weather, setWeather] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.myWeather()
      .then(setWeather)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <div className="page mobile-flow-page">
      <header className="page-header simple-header">
        <span className="eyebrow">Weather</span>
        <h2>Today on your farm</h2>
      </header>
      <ErrorAlert error={error} />
      {!weather ? (
        <EmptyState title="Weather unavailable" message="Add district in profile to get local advisory." />
      ) : (
        <>
          <section className="weather-hero-card">
            <div>
              <span>{weather.resolved_location}</span>
              <strong>{weather.current?.temperature_c ?? "-"} C</strong>
              <p>Humidity {weather.current?.humidity_percent ?? "-"}%</p>
            </div>
            <SunMedium size={54} />
          </section>

          <section className="simple-card-grid">
            <article className="info-card"><CloudRain /><span>Rain</span><strong>{weather.current?.rainfall_mm ?? 0} mm</strong></article>
            <article className="info-card"><Wind /><span>Wind</span><strong>{weather.current?.wind_speed_kmh ?? "-"} km/h</strong></article>
            <article className="info-card"><Leaf /><span>Spray</span><strong>{weather.spray_window?.decision?.replaceAll("_", " ")}</strong><p>{weather.spray_window?.reason}</p></article>
            <article className="info-card"><Droplets /><span>Irrigation</span><strong>{weather.irrigation?.decision?.replaceAll("_", " ")}</strong><p>{weather.irrigation?.reason}</p></article>
          </section>

          <section className="panel">
            <h3>Crop advisory</h3>
            <p>{weather.forecast_3days}</p>
          </section>
        </>
      )}
    </div>
  );
}
