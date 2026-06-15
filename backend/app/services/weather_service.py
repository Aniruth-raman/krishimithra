from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


class WeatherLookupError(RuntimeError):
    pass


def _first(values: Optional[List[Any]], default: Any = None) -> Any:
    return values[0] if values else default


def _format_forecast(daily: Dict[str, Any]) -> str:
    days = daily.get("time") or []
    rain = daily.get("precipitation_sum") or []
    rain_probability = daily.get("precipitation_probability_max") or []
    wind = daily.get("wind_speed_10m_max") or []
    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    parts = []
    for index, day in enumerate(days[:3]):
        parts.append(
            f"{day}: {lows[index] if index < len(lows) else '-'}-{highs[index] if index < len(highs) else '-'}°C, "
            f"rain {rain[index] if index < len(rain) else 0} mm, "
            f"rain chance {rain_probability[index] if index < len(rain_probability) else 0}%, "
            f"wind {wind[index] if index < len(wind) else 0} km/h"
        )
    return "; ".join(parts) or "Forecast unavailable."


def _spray_window(current: Dict[str, Any], daily: Dict[str, Any]) -> Dict[str, Any]:
    rainfall = float(current.get("precipitation") or current.get("rain") or 0)
    wind_speed = float(current.get("wind_speed_10m") or 0)
    rain_probability = _first(daily.get("precipitation_probability_max"), 0) or 0
    rain_sum = _first(daily.get("precipitation_sum"), 0) or 0

    if rainfall > 0 or rain_sum >= 2 or rain_probability >= 60:
        decision = "delay_spraying"
        reason = "Rain is present or likely, so spray may wash off and become ineffective."
    elif wind_speed >= 18:
        decision = "avoid_spraying"
        reason = "Wind is high enough to increase drift risk."
    else:
        decision = "suitable_with_caution"
        reason = "Rain and wind risk are currently low; still verify product label and local conditions."

    return {
        "decision": decision,
        "reason": reason,
        "wind_speed_kmh": wind_speed,
        "rainfall_mm": rainfall,
        "rain_probability_percent": rain_probability,
    }


def _irrigation_advice(current: Dict[str, Any], daily: Dict[str, Any]) -> Dict[str, Any]:
    temperature = float(current.get("temperature_2m") or 0)
    humidity = float(current.get("relative_humidity_2m") or 0)
    rain_sum = sum(float(value or 0) for value in (daily.get("precipitation_sum") or [])[:3])

    if rain_sum >= 10:
        decision = "skip_or_reduce"
        reason = "Forecast rainfall should cover part of the crop water need; avoid waterlogging."
    elif temperature >= 34 and humidity < 55:
        decision = "irrigate_early"
        reason = "Hot and relatively dry conditions can increase crop water stress."
    else:
        decision = "monitor_soil"
        reason = "No strong irrigation trigger from weather alone; check soil moisture and crop stage."

    return {"decision": decision, "reason": reason, "forecast_rain_3d_mm": round(rain_sum, 1)}


async def fetch_weather(location: str) -> Dict[str, Any]:
    location = (location or "").strip()
    if not location:
        raise WeatherLookupError("Location is required for weather lookup.")

    async with httpx.AsyncClient(timeout=12) as client:
        geo_response = await client.get(
            GEOCODING_URL,
            params={"name": location, "count": 1, "language": "en", "format": "json"},
        )
        geo_response.raise_for_status()
        results = geo_response.json().get("results") or []
        if not results:
            raise WeatherLookupError(f"Could not find weather coordinates for {location}.")

        place = results[0]
        forecast_response = await client.get(
            FORECAST_URL,
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,precipitation,rain,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max",
                "forecast_days": 3,
                "timezone": "auto",
            },
        )
        forecast_response.raise_for_status()

    payload = forecast_response.json()
    current = payload.get("current") or {}
    daily = payload.get("daily") or {}
    resolved_name = ", ".join(
        part for part in [place.get("name"), place.get("admin1"), place.get("country")] if part
    )

    return {
        "location": location,
        "resolved_location": resolved_name or location,
        "latitude": place.get("latitude"),
        "longitude": place.get("longitude"),
        "provider": "open-meteo",
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "current": {
            "temperature_c": current.get("temperature_2m"),
            "humidity_percent": current.get("relative_humidity_2m"),
            "rainfall_mm": current.get("precipitation") or current.get("rain") or 0,
            "wind_speed_kmh": current.get("wind_speed_10m"),
            "time": current.get("time"),
        },
        "daily": daily,
        "forecast_3days": _format_forecast(daily),
        "spray_window": _spray_window(current, daily),
        "irrigation": _irrigation_advice(current, daily),
    }
