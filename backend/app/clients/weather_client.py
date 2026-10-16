"""Marine weather client integrating Open-Meteo Marine & Forecast APIs with SQLite caching."""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
import httpx
from app.config import get_settings
from app.db.session import get_db_context
from app.models.external_cache import ExternalWeatherCache
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
    """Client for external Open-Meteo Marine & Forecast APIs with SQLite caching (no simulated fallbacks)."""

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        settings = get_settings()
        self.base_url = base_url or settings.OPENMETEO_BASE_URL
        self.forecast_url = "https://api.open-meteo.com/v1/forecast"
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS
        self._cache: Dict[str, Tuple[float, WeatherMetrics]] = {}
        self.cache_ttl_seconds: float = 1800.0  # 30 minutes TTL

    def _persist_weather_cache(
        self,
        cache_key: str,
        lat: float,
        lon: float,
        port_id: str,
        metrics: WeatherMetrics,
        source: str,
    ) -> None:
        """Persist or update weather metrics in SQLite database."""
        try:
            with get_db_context() as db:
                record = db.query(ExternalWeatherCache).filter(
                    (ExternalWeatherCache.id == cache_key)
                    | (
                        (ExternalWeatherCache.lat == round(lat, 2))
                        & (ExternalWeatherCache.lon == round(lon, 2))
                    )
                ).first()
                if not record and port_id:
                    record = (
                        db.query(ExternalWeatherCache)
                        .filter(ExternalWeatherCache.port_id == port_id)
                        .first()
                    )

                now_utc = datetime.now(timezone.utc)
                if not record:
                    record = ExternalWeatherCache(
                        id=cache_key,
                        lat=round(lat, 2),
                        lon=round(lon, 2),
                        port_id=port_id or None,
                        wind_speed_knots=metrics.windSpeedKnots,
                        gust_speed_knots=metrics.gustSpeedKnots,
                        wave_height_m=metrics.waveHeightM,
                        swell_period_sec=metrics.swellPeriodSec,
                        visibility_nm=metrics.visibilityNm,
                        source=source,
                        fetched_at=now_utc,
                    )
                    db.add(record)
                else:
                    record.lat = round(lat, 2)
                    record.lon = round(lon, 2)
                    if port_id:
                        record.port_id = port_id
                    record.wind_speed_knots = metrics.windSpeedKnots
                    record.gust_speed_knots = metrics.gustSpeedKnots
                    record.wave_height_m = metrics.waveHeightM
                    record.swell_period_sec = metrics.swellPeriodSec
                    record.visibility_nm = metrics.visibilityNm
                    record.source = source
                    record.fetched_at = now_utc
                db.commit()
        except Exception as e:
            logger.warning("Failed to persist weather metrics to SQLite: %s", str(e))

    async def get_marine_weather(
        self, lat: float, lon: float, port_id: str = "", force_refresh: bool = False
    ) -> WeatherMetrics:
        """Fetch real-time marine weather metrics from Open-Meteo with SQLite caching (< 30 min freshness)."""
        cache_key = f"{round(lat, 2)}:{round(lon, 2)}"
        now = time.time()
        stale_cached_metrics: Optional[WeatherMetrics] = None

        # 1. Check SQLite for cached data (< 30 minutes old)
        try:
            with get_db_context() as db:
                query = db.query(ExternalWeatherCache).filter(
                    (ExternalWeatherCache.id == cache_key)
                    | (
                        (ExternalWeatherCache.lat == round(lat, 2))
                        & (ExternalWeatherCache.lon == round(lon, 2))
                    )
                )
                cached_record = query.first()
                if not cached_record and port_id:
                    cached_record = (
                        db.query(ExternalWeatherCache)
                        .filter(ExternalWeatherCache.port_id == port_id)
                        .first()
                    )

                if cached_record:
                    stale_cached_metrics = cached_record.to_pydantic()
                    if not force_refresh and cached_record.is_fresh(
                        max_age_seconds=self.cache_ttl_seconds
                    ):
                        self._cache[cache_key] = (now, stale_cached_metrics)
                        return stale_cached_metrics
        except Exception as e:
            logger.debug("Database weather cache lookup failed: %s", str(e))

        if not force_refresh and cache_key in self._cache:
            cached_time, cached_metrics = self._cache[cache_key]
            if now - cached_time < self.cache_ttl_seconds:
                return cached_metrics

        # 2. Query external Open-Meteo Marine & Forecast APIs
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "wave_height,swell_wave_period,wave_period",
            "hourly": "wind_speed_10m,wind_gusts_10m",
            "wind_speed_unit": "kn",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            wave_height = 0.0
            swell_period = 0.0
            wind_speed = 0.0
            wind_gust = 0.0
            visibility_nm = 10.0
            got_wind = False
            got_visibility = False

            marine_resp = await client.get(self.base_url, params=params)
            marine_resp.raise_for_status()
            marine_data = marine_resp.json()
            current = marine_data.get("current", {})
            hourly = marine_data.get("hourly", {})

            raw_wave = current.get("wave_height")
            if raw_wave is not None:
                wave_height = _safe_float(raw_wave, 0.0)

            raw_swell = current.get("swell_wave_period")
            if raw_swell is None:
                raw_swell = current.get("wave_period")
            if raw_swell is not None:
                swell_period = _safe_float(raw_swell, 0.0)

            if current.get("visibility") is not None:
                vis_m = _safe_float(current.get("visibility"), 18520.0)
                visibility_nm = round(vis_m / 1852.0, 1)
                got_visibility = True

            wind_speeds = [w for w in hourly.get("wind_speed_10m", []) if w is not None]
            wind_gusts = [g for g in hourly.get("wind_gusts_10m", []) if g is not None]
            if wind_speeds:
                wind_speed = _safe_float(wind_speeds[0], 0.0)
                wind_gust = _safe_float(wind_gusts[0] if wind_gusts else None, wind_speed)
                got_wind = True

            if not got_wind or not got_visibility:
                forecast_params = {
                    "latitude": lat,
                    "longitude": lon,
                    "current": "wind_speed_10m,wind_gusts_10m,visibility",
                    "wind_speed_unit": "kn",
                }
                try:
                    forecast_resp = await client.get(self.forecast_url, params=forecast_params)
                    if forecast_resp.status_code == 200:
                        fdata = forecast_resp.json()
                        fcurr = fdata.get("current", {})
                        if not got_wind and fcurr.get("wind_speed_10m") is not None:
                            wind_speed = _safe_float(fcurr.get("wind_speed_10m"), wind_speed)
                            wind_gust = _safe_float(fcurr.get("wind_gusts_10m"), wind_speed)
                        if not got_visibility and fcurr.get("visibility") is not None:
                            vis_m = _safe_float(fcurr.get("visibility"), 18520.0)
                            visibility_nm = round(vis_m / 1852.0, 1)
                except Exception as e:
                    logger.debug("Open-Meteo forecast supplement call failed: %s", str(e))

            metrics = WeatherMetrics(
                windSpeedKnots=round(wind_speed, 1),
                gustSpeedKnots=round(wind_gust, 1),
                waveHeightM=round(wave_height, 1),
                swellPeriodSec=round(swell_period, 1),
                visibilityNm=round(visibility_nm, 1),
            )
            self._persist_weather_cache(
                cache_key, lat, lon, port_id, metrics, source="open-meteo"
            )
            self._cache[cache_key] = (now, metrics)
            return metrics


