"""SQLAlchemy models for caching external API data (weather and AIS vessel traffic) with fetched_at timestamps."""

from datetime import datetime, timezone
from typing import Optional, Tuple
from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.risk import CongestionMetrics, NavigationalMetrics, TerminalMetrics, WeatherMetrics


class ExternalWeatherCache(Base):
    """Persisted external marine weather telemetry with fetched_at timestamp."""

    __tablename__ = "external_weather_cache"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g., "{round(lat,2)}:{round(lon,2)}"
    lat: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    lon: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    port_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    wind_speed_knots: Mapped[float] = mapped_column(Float, nullable=False)
    gust_speed_knots: Mapped[float] = mapped_column(Float, nullable=False)
    wave_height_m: Mapped[float] = mapped_column(Float, nullable=False)
    swell_period_sec: Mapped[float] = mapped_column(Float, nullable=False)
    visibility_nm: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="open-meteo", nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("ix_weather_coords", "lat", "lon"),
    )

    def is_fresh(self, max_age_seconds: float = 1800.0) -> bool:
        """Check if cached weather record was fetched less than max_age_seconds ago (default 30 mins)."""
        now = datetime.now(timezone.utc)
        fetched = self.fetched_at
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        return (now - fetched).total_seconds() < max_age_seconds

    def to_pydantic(self) -> WeatherMetrics:
        """Convert database record to Pydantic WeatherMetrics."""
        return WeatherMetrics(
            windSpeedKnots=self.wind_speed_knots,
            gustSpeedKnots=self.gust_speed_knots,
            waveHeightM=self.wave_height_m,
            swellPeriodSec=self.swell_period_sec,
            visibilityNm=self.visibility_nm,
        )


class ExternalAISTrafficCache(Base):
    """Persisted external vessel traffic metrics from AISStream with fetched_at timestamp."""

    __tablename__ = "external_ais_traffic_cache"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g., "{port_id}:{vessel_class}"
    port_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    locode: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    vessel_class: Mapped[str] = mapped_column(String(50), nullable=False)

    # Congestion Metrics
    anchorage_queue_count: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_waiting_time_hours: Mapped[float] = mapped_column(Float, nullable=False)
    berth_occupancy_pct: Mapped[float] = mapped_column(Float, nullable=False)
    rolling_30d_avg_queue: Mapped[float] = mapped_column(Float, nullable=False)
    rolling_30d_avg_wait_hours: Mapped[float] = mapped_column(Float, nullable=False)

    # Terminal Metrics
    berth_turnaround_hours: Mapped[float] = mapped_column(Float, nullable=False)
    berth_to_anchorage_wait_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    dwell_time_anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    rolling_30d_avg_turnaround: Mapped[float] = mapped_column(Float, nullable=False)

    # Navigational Metrics
    under_keel_clearance_m: Mapped[float] = mapped_column(Float, nullable=False)
    channel_depth_m: Mapped[float] = mapped_column(Float, nullable=False)
    air_draft_clearance_m: Mapped[float] = mapped_column(Float, nullable=False)
    pilotage_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tide_height_m: Mapped[float] = mapped_column(Float, nullable=False)

    source: Mapped[str] = mapped_column(String(50), default="aisstream", nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("ix_ais_port_class", "port_id", "vessel_class"),
    )

    def is_fresh(self, max_age_seconds: float = 1800.0) -> bool:
        """Check if cached traffic record was fetched less than max_age_seconds ago (default 30 mins)."""
        now = datetime.now(timezone.utc)
        fetched = self.fetched_at
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        return (now - fetched).total_seconds() < max_age_seconds

    def to_pydantic(self) -> Tuple[CongestionMetrics, TerminalMetrics, NavigationalMetrics]:
        """Convert database record to tuple of Pydantic metric models."""
        congestion = CongestionMetrics(
            anchorageQueueCount=self.anchorage_queue_count,
            avgWaitingTimeHours=self.avg_waiting_time_hours,
            berthOccupancyPct=self.berth_occupancy_pct,
            rolling30dAvgQueue=self.rolling_30d_avg_queue,
            rolling30dAvgWaitHours=self.rolling_30d_avg_wait_hours,
        )
        terminal = TerminalMetrics(
            berthTurnaroundHours=self.berth_turnaround_hours,
            berthToAnchorageWaitRatio=self.berth_to_anchorage_wait_ratio,
            dwellTimeAnomalyScore=self.dwell_time_anomaly_score,
            rolling30dAvgTurnaround=self.rolling_30d_avg_turnaround,
        )
        navigational = NavigationalMetrics(
            underKeelClearanceM=self.under_keel_clearance_m,
            channelDepthM=self.channel_depth_m,
            airDraftClearanceM=self.air_draft_clearance_m,
            pilotageAvailable=self.pilotage_available,
            tideHeightM=self.tide_height_m,
        )
        return congestion, terminal, navigational
