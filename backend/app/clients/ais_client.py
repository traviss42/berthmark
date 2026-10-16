"""AIS and vessel traffic API client with fallback simulation."""

import logging
from typing import Optional, Tuple
import httpx
from app.config import get_settings
from app.models.risk import CongestionMetrics, NavigationalMetrics, TerminalMetrics

logger = logging.getLogger(__name__)


class AISClient:
    """Client for external AIS stream & traffic metrics API with fallback simulation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.AISSTREAM_API_KEY
        self.base_url = base_url or settings.AISSTREAM_BASE_URL
        self.timeout = timeout or settings.HTTP_TIMEOUT_SECONDS

    def _generate_fallback_metrics(
        self, port_id: str, vessel_class: str
    ) -> Tuple[CongestionMetrics, TerminalMetrics, NavigationalMetrics]:
        """Deterministic realistic metrics based on port and vessel class seed."""
        seed = sum(ord(c) for c in f"{port_id}:{vessel_class}")

        # Baseline queue and wait
        base_queue = 8 + (seed % 15)
        queue_count = int(base_queue * (0.8 + ((seed % 7) * 0.1)))
        avg_wait = round(16.0 + (seed % 20) + ((seed % 5) * 1.5), 1)
        base_wait = round(avg_wait * (0.85 + ((seed % 4) * 0.08)), 1)
        occupancy = float(60 + (seed % 35))

        congestion = CongestionMetrics(
            anchorageQueueCount=queue_count,
            avgWaitingTimeHours=avg_wait,
            berthOccupancyPct=occupancy,
            rolling30dAvgQueue=float(base_queue),
            rolling30dAvgWaitHours=base_wait,
        )

        # Terminal
        base_turnaround = 24.0 + (seed % 18)
        turnaround = round(base_turnaround * (0.9 + ((seed % 6) * 0.1)), 1)
        wait_ratio = round(0.4 + ((seed % 6) * 0.08), 2)
        dwell_score = float(30 + (seed % 45))

        terminal = TerminalMetrics(
            berthTurnaroundHours=turnaround,
            berthToAnchorageWaitRatio=wait_ratio,
            dwellTimeAnomalyScore=dwell_score,
            rolling30dAvgTurnaround=round(base_turnaround, 1),
        )

        # Navigational
        ukc = round(1.5 + ((seed % 15) * 0.2), 1)
        depth = round(14.0 + (seed % 8), 1)
        air_draft = round(6.0 + (seed % 8), 1)
        pilotage = (seed % 9) != 0  # 90% chance available

        navigational = NavigationalMetrics(
            underKeelClearanceM=ukc,
            channelDepthM=depth,
            airDraftClearanceM=air_draft,
            pilotageAvailable=pilotage,
            tideHeightM=round(1.0 + ((seed % 10) * 0.2), 1),
        )

        return congestion, terminal, navigational

    async def get_port_traffic_metrics(
        self, port_id: str, locode: str, vessel_class: str
    ) -> Tuple[CongestionMetrics, TerminalMetrics, NavigationalMetrics]:
        """Fetch AIS and operational metrics from external API, falling back gracefully if offline/unconfigured."""
        if self.api_key and self.base_url:
            try:
                headers = {"Authorization": f"Bearer {self.api_key}"}
                params = {"port": locode, "vesselClass": vessel_class}
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(
                        f"{self.base_url}/metrics", headers=headers, params=params
                    )
                    if response.status_code == 200:
                        data = response.json()
                        return (
                            CongestionMetrics(**data["congestion"]),
                            TerminalMetrics(**data["terminal"]),
                            NavigationalMetrics(**data["navigational"]),
                        )
                    else:
                        logger.warning(
                            "AIS API returned status %d. Utilizing fallback metrics.",
                            response.status_code,
                        )
            except Exception as e:
                logger.warning("AIS API call failed: %s. Utilizing fallback.", str(e))

        return self._generate_fallback_metrics(port_id, vessel_class)
