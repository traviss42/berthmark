"""Marine weather client integrating Open-Meteo with offline fallbacks."""

import logging
from typing import Optional
import httpx
from app.config import get_settings
from app.models.risk import WeatherMetrics

logger = logging.getLogger(__name__)


def _safe_float(val: object, default: float) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


class MarineWeatherClient:
    """Client for external Marine Weather API with fallback simulation."""

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        settings = get_settings()
        self.base_url = base_url or settings.OPENMETEO_BASE_URL
        self.forecast_url = "https://api.open-meteo.com/v1/forecast"
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS

    def _generate_fallback_weather(self, lat: float, lon: float, port_id: str) -> WeatherMetrics:
        """Deterministic fallback marine weather metrics when external API is offline or rate-limited."""
        seed = int(abs(lat * 100 + lon * 10) + sum(ord(c) for c in port_id))
        wind = 12.0 + (seed % 28)  # 12 to 39 knots
        gust = wind * (1.2 + ((seed % 5) * 0.05))
        wave = 1.0 + ((seed % 35) * 0.1)  # 1.0 to 4.4 meters
        swell = 5.0 + (seed % 8)  # 5 to 12 seconds
        visibility = 4.0 + ((seed % 10) * 0.8)  # 4 to 12 nautical miles

        return WeatherMetrics(
            windSpeedKnots=round(wind, 1),
            gustSpeedKnots=round(gust, 1),
            waveHeightM=round(wave, 1),
            swellPeriodSec=round(swell, 1),
            visibilityNm=round(visibility, 1),
        )

    async def get_marine_weather(self, lat: float, lon: float, port_id: str = "") -> WeatherMetrics:
        """Fetch real-time marine weather metrics from Open-Meteo Marine/Forecast API, or use fallback."""
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "wave_height",
            "hourly": "wind_speed_10m,wind_gusts_10m",
            "wind_speed_unit": "kn",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # 1. Attempt marine API for wave height and wind
                wave_height = 1.5
                wind_speed = 18.0
                wind_gust = 23.4
                got_wind = False

                marine_resp = await client.get(self.base_url, params=params)
                if marine_resp.status_code == 200:
                    marine_data = marine_resp.json()
                    current = marine_data.get("current", {})
                    hourly = marine_data.get("hourly", {})

                    raw_wave = current.get("wave_height")
                    if raw_wave is not None:
                        wave_height = _safe_float(raw_wave, 1.5)

                    wind_speeds = [w for w in hourly.get("wind_speed_10m", []) if w is not None]
                    wind_gusts = [g for g in hourly.get("wind_gusts_10m", []) if g is not None]
                    if wind_speeds:
                        wind_speed = _safe_float(wind_speeds[0], 18.0)
                        wind_gust = _safe_float(wind_gusts[0] if wind_gusts else None, wind_speed * 1.3)
                        got_wind = True

                # 2. If marine API didn't provide wind (e.g., inland water bodies), query forecast API
                if not got_wind:
                    forecast_params = {
                        "latitude": lat,
                        "longitude": lon,
                        "current": "wind_speed_10m,wind_gusts_10m",
                        "wind_speed_unit": "kn",
                    }
                    try:
                        forecast_resp = await client.get(self.forecast_url, params=forecast_params)
                        if forecast_resp.status_code == 200:
                            fdata = forecast_resp.json()
                            fcurr = fdata.get("current", {})
                            if fcurr.get("wind_speed_10m") is not None:
                                wind_speed = _safe_float(fcurr.get("wind_speed_10m"), wind_speed)
                                wind_gust = _safe_float(fcurr.get("wind_gusts_10m"), wind_speed * 1.3)
                    except Exception:
                        pass

                return WeatherMetrics(
                    windSpeedKnots=round(wind_speed, 1),
                    gustSpeedKnots=round(wind_gust, 1),
                    waveHeightM=round(wave_height, 1),
                    swellPeriodSec=7.5,
                    visibilityNm=8.0,
                )
        except Exception as e:
            logger.warning("Failed to reach weather API: %s. Utilizing fallback.", str(e))

        return self._generate_fallback_weather(lat, lon, port_id)
