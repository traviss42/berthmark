"""Open-Meteo Weather and Marine Ingestion Client with TTL caching and persistence."""

import asyncio
import logging
import time
import uuid
from typing import Any
import httpx
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.database import get_session_factory
from backend.models import PortRiskSnapshot, utc_now

logger = logging.getLogger(__name__)

# Constants
KMH_TO_KNOTS = 0.539957
MS_TO_KNOTS = 1.94384
METERS_TO_NM = 1 / 1852.0
DEFAULT_TIMEOUT = 10.0
DEFAULT_CACHE_TTL = 900.0  # 15 minutes


class WeatherMetrics(BaseModel):
    """Normalized weather and marine metrics conforming to OpenAPI WeatherMetrics schema."""

    model_config = ConfigDict(populate_by_name=True)

    windSpeedKnots: float = Field(..., ge=0.0, description="Sustained wind speed in knots.")
    waveHeightM: float = Field(..., ge=0.0, description="Significant wave height in meters.")
    swellPeriodSec: float = Field(..., ge=0.0, description="Primary wave/swell period in seconds.")
    visibilityNm: float = Field(..., ge=0.0, description="Meteorological visibility in nautical miles.")
    gustSpeedKnots: float = Field(..., ge=0.0, description="Peak wind gusts in knots.")


class TideResult(BaseModel):
    """Dynamic sea level / tidal elevation offset result with fallback status."""

    model_config = ConfigDict(populate_by_name=True)

    tide_offset_m: float = Field(default=0.0, description="Dynamic tide water elevation above MLLW in meters.")
    tide_data_available: bool = Field(default=False, description="Flag indicating if live tide API responded.")
    source: str = Field(default="fallback", description="Data source or fallback indicator.")


def compute_weather_risk(metrics: WeatherMetrics) -> str:
    """Evaluate atmospheric and oceanographic risk tier based on PIANC and operational limits.

    Returns:
        'HIGH' if waveHeightM > 2.5 or windSpeedKnots > 30.0 or gustSpeedKnots > 40.0
        'MEDIUM' if waveHeightM >= 1.5 or windSpeedKnots > 20.0 or gustSpeedKnots > 28.0
        'LOW' otherwise
    """
    if (
        metrics.waveHeightM > 2.5
        or metrics.windSpeedKnots > 30.0
        or metrics.gustSpeedKnots > 40.0
    ):
        return "HIGH"
    if (
        metrics.waveHeightM >= 1.5
        or metrics.windSpeedKnots > 20.0
        or metrics.gustSpeedKnots > 28.0
    ):
        return "MEDIUM"
    return "LOW"


class WeatherClient:
    """Asynchronous client for Open-Meteo Marine and Forecast APIs with TTL caching."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        ttl_seconds: float = DEFAULT_CACHE_TTL,
        marine_api_url: str = "https://marine-api.open-meteo.com/v1/marine",
        forecast_api_url: str = "https://api.open-meteo.com/v1/forecast",
        http_client: httpx.AsyncClient | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.timeout = timeout
        self.ttl_seconds = ttl_seconds
        self.marine_api_url = marine_api_url
        self.forecast_api_url = forecast_api_url
        self.http_client = http_client
        self.session_factory = session_factory
        # Cache keyed by (round(lat, 2), round(lon, 2)) -> (WeatherMetrics, timestamp)
        self._cache: dict[tuple[float, float], tuple[WeatherMetrics, float]] = {}
        # Cache keyed by (round(lat, 2), round(lon, 2)) -> (TideResult, timestamp)
        self._tide_cache: dict[tuple[float, float], tuple[TideResult, float]] = {}

    def clear_cache(self) -> None:
        """Clear all entries in the in-memory TTL cache."""
        self._cache.clear()
        self._tide_cache.clear()

    async def _fetch_marine_data(
        self, client: httpx.AsyncClient, lat: float, lon: float
    ) -> dict[str, Any] | None:
        """Fetch oceanographic wave and swell data from Open-Meteo Marine API."""
        try:
            params = {
                "latitude": lat,
                "longitude": lon,
                "current": "wave_height,wave_period",
            }
            res = await client.get(self.marine_api_url, params=params)
            if res.is_success:
                return res.json()
            # If 400 or other client/server error (e.g. inland coordinates)
            logger.info("Marine API returned status %s for (%s, %s)", res.status_code, lat, lon)
            return None
        except Exception as exc:
            logger.warning("Marine API request failed for (%s, %s): %s", lat, lon, exc)
            return None

    async def _fetch_forecast_data(
        self, client: httpx.AsyncClient, lat: float, lon: float
    ) -> dict[str, Any] | None:
        """Fetch atmospheric wind, gusts, and visibility from Open-Meteo Forecast API."""
        try:
            params = {
                "latitude": lat,
                "longitude": lon,
                "current": "wind_speed_10m,wind_gusts_10m,visibility",
            }
            res = await client.get(self.forecast_api_url, params=params)
            if res.is_success:
                return res.json()
            logger.warning("Forecast API returned status %s for (%s, %s)", res.status_code, lat, lon)
            return None
        except Exception as exc:
            logger.warning("Forecast API request failed for (%s, %s): %s", lat, lon, exc)
            return None

    async def get_weather(
        self, lat: float, lon: float, unlocode: str | None = None
    ) -> WeatherMetrics:
        """Fetch real-time weather metrics with TTL caching, unit conversions, and DB persistence."""
        cache_key = (round(lat, 2), round(lon, 2))
        now = time.time()

        # Check in-memory cache
        if cache_key in self._cache:
            cached_metrics, cached_at = self._cache[cache_key]
            if now - cached_at < self.ttl_seconds:
                # Cache hit within valid TTL window
                return cached_metrics

        # Create or use provided async HTTP client
        if self.http_client is not None:
            marine_data, forecast_data = await asyncio.gather(
                self._fetch_marine_data(self.http_client, lat, lon),
                self._fetch_forecast_data(self.http_client, lat, lon),
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                marine_data, forecast_data = await asyncio.gather(
                    self._fetch_marine_data(client, lat, lon),
                    self._fetch_forecast_data(client, lat, lon),
                )

        # Handle complete failure of forecast data: return stale cached metrics or safe defaults
        if forecast_data is None:
            if cache_key in self._cache:
                logger.info("Using stale cached metrics for (%s, %s) due to upstream failure", lat, lon)
                return self._cache[cache_key][0]
            # Safe default
            default_metrics = WeatherMetrics(
                windSpeedKnots=0.0,
                waveHeightM=0.0,
                swellPeriodSec=0.0,
                visibilityNm=10.0,
                gustSpeedKnots=0.0,
            )
            return default_metrics

        # Parse marine swell data (gracefully fallback to 0.0 for inland coordinates)
        wave_height_m = 0.0
        swell_period_sec = 0.0
        if marine_data and "current" in marine_data:
            curr_marine = marine_data["current"]
            raw_wh = curr_marine.get("wave_height")
            if raw_wh is not None:
                wave_height_m = max(0.0, float(raw_wh))
            raw_wp = curr_marine.get("wave_period")
            if raw_wp is not None:
                swell_period_sec = max(0.0, float(raw_wp))

        # Parse forecast atmospheric data
        curr_fc = forecast_data.get("current", {})
        units_fc = forecast_data.get("current_units", {})

        # Wind speed conversion
        wind_unit = units_fc.get("wind_speed_10m", "km/h")
        if wind_unit == "m/s":
            wind_factor = MS_TO_KNOTS
        elif wind_unit in ("kn", "knots", "knot"):
            wind_factor = 1.0
        else:
            wind_factor = KMH_TO_KNOTS

        raw_wind = curr_fc.get("wind_speed_10m")
        if raw_wind is not None:
            wind_speed_kts = max(0.0, round(float(raw_wind) * wind_factor, 1))
        else:
            wind_speed_kts = 0.0

        # Wind gusts conversion
        raw_gusts = curr_fc.get("wind_gusts_10m")
        if raw_gusts is not None:
            gust_speed_kts = max(0.0, round(float(raw_gusts) * wind_factor, 1))
            if gust_speed_kts < wind_speed_kts:
                gust_speed_kts = wind_speed_kts
        else:
            gust_speed_kts = wind_speed_kts

        # Visibility conversion (reported in meters by Open-Meteo)
        raw_vis = curr_fc.get("visibility")
        if raw_vis is not None:
            visibility_nm = max(0.0, round(float(raw_vis) * METERS_TO_NM, 1))
        else:
            visibility_nm = 10.0

        metrics = WeatherMetrics(
            windSpeedKnots=wind_speed_kts,
            waveHeightM=wave_height_m,
            swellPeriodSec=swell_period_sec,
            visibilityNm=visibility_nm,
            gustSpeedKnots=gust_speed_kts,
        )

        # Update cache
        self._cache[cache_key] = (metrics, now)

        # Persist observation asynchronously if unlocode provided
        if unlocode:
            await self._persist_snapshot(unlocode, metrics)

        return metrics

    async def _persist_snapshot(self, unlocode: str, metrics: WeatherMetrics) -> None:
        """Persist weather metrics into port_risk_snapshots in a short-lived DB session."""
        session_factory = self.session_factory or get_session_factory()
        risk_level = compute_weather_risk(metrics)
        try:
            async with session_factory() as session:
                stmt = select(PortRiskSnapshot).where(PortRiskSnapshot.unlocode == unlocode)
                result = await session.execute(stmt)
                snapshot = result.scalars().first()
                if snapshot:
                    snapshot.swell_height_m = metrics.waveHeightM
                    snapshot.wind_speed_kts = metrics.windSpeedKnots
                    snapshot.weather_risk_level = risk_level
                    snapshot.updated_at = utc_now()
                else:
                    snapshot = PortRiskSnapshot(
                        snapshot_id=uuid.uuid4(),
                        unlocode=unlocode,
                        vessel_class_id="panamax",
                        weather_risk_level=risk_level,
                        swell_height_m=metrics.waveHeightM,
                        wind_speed_kts=metrics.windSpeedKnots,
                        updated_at=utc_now(),
                    )
                    session.add(snapshot)
                await session.commit()
        except Exception as exc:
            logger.warning("Failed to persist weather snapshot for %s: %s", unlocode, exc)

    async def get_tide_offset(
        self, lat: float, lon: float, client: httpx.AsyncClient | None = None
    ) -> TideResult:
        """Fetch real-time sea level / tide height above MLLW in meters.

        Queries Open-Meteo Marine API or NOAA CO-OPS REST API.
        If offline, unreachable, or null response, defaults to 0.0m offset
        with tide_data_available = False.
        """
        cache_key = (round(lat, 2), round(lon, 2))
        now = time.time()

        if cache_key in self._tide_cache:
            cached_res, cached_at = self._tide_cache[cache_key]
            if now - cached_at < self.ttl_seconds:
                return cached_res

        tide_result = await self._fetch_tide_data(lat, lon, client=client)
        self._tide_cache[cache_key] = (tide_result, now)
        return tide_result

    async def _fetch_tide_data(
        self, lat: float, lon: float, client: httpx.AsyncClient | None = None
    ) -> TideResult:
        """Fetch sea level height from Open-Meteo Marine or NOAA API with fallback."""
        try:
            params = {
                "latitude": lat,
                "longitude": lon,
                "current": "sea_level_height_above_mean_sea_level",
            }
            if client is not None:
                res = await client.get(self.marine_api_url, params=params)
            elif self.http_client is not None:
                res = await self.http_client.get(self.marine_api_url, params=params)
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as local_client:
                    res = await local_client.get(self.marine_api_url, params=params)

            if res.is_success:
                data = res.json()
                current_block = data.get("current") or {}
                sea_level = current_block.get("sea_level_height_above_mean_sea_level")
                if sea_level is not None:
                    offset = round(float(sea_level), 2)
                    return TideResult(
                        tide_offset_m=offset,
                        tide_data_available=True,
                        source="open-meteo-marine",
                    )

            logger.info("Live tide endpoint returned non-success or empty for (%s, %s)", lat, lon)
            return TideResult(tide_offset_m=0.0, tide_data_available=False, source="fallback")
        except Exception as exc:
            logger.warning(
                "Tide API request failed for (%s, %s): %s; defaulting to 0.0m baseline",
                lat,
                lon,
                exc,
            )
            return TideResult(tide_offset_m=0.0, tide_data_available=False, source="fallback")


# Global default client instance
_default_weather_client: WeatherClient | None = None


def get_weather_client() -> WeatherClient:
    """Get or create singleton WeatherClient."""
    global _default_weather_client
    if _default_weather_client is None:
        _default_weather_client = WeatherClient()
    return _default_weather_client


async def fetch_tide_offset(
    lat: float,
    lon: float,
    client: httpx.AsyncClient | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> TideResult:
    """Fetch live tide offset with automatic fallback to static 0.0m MLLW baseline."""
    weather_client = get_weather_client()
    return await weather_client.get_tide_offset(lat, lon, client=client)
