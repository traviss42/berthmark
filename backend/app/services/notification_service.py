"""Notification service managing in-app alerts and risk state transitions with database persistence."""

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from app.db.models import MonitoredPort, NotificationRecord
from app.db.session import get_db_context
from app.models.common import RiskTier
from app.models.notification import CreateAlertRequest, Notification

logger = logging.getLogger("berthmark.notifications")

TIER_LABELS: Dict[RiskTier, str] = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
}


class NotificationService:
    """Manages user alerts, state-change triggers, and read status backed by SQLAlchemy database."""

    EMAIL_COOLDOWN_SECONDS: float = 1800.0  # 30-minute cooldown between email alerts per user and port

    def __init__(self) -> None:
        # In-memory tracking of (user_id, port_id) -> timestamp of last outbound email dispatched
        self._last_email_sent: Dict[Tuple[str, str], float] = {}

    def is_email_cooldown_active(self, user_id: str, port_id: str) -> bool:
        """Check whether outbound warning emails are within the 30-minute cooldown window for a user and port."""
        uid = user_id.strip().lower()
        pid = port_id.strip().lower()
        now = time.time()

        last_time = self._last_email_sent.get((uid, pid))
        if last_time is not None:
            return (now - last_time) < self.EMAIL_COOLDOWN_SECONDS

        # Fallback to database for cold starts or service restarts
        try:
            with get_db_context() as db:
                cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.EMAIL_COOLDOWN_SECONDS)
                recent = (
                    db.query(NotificationRecord)
                    .filter(
                        NotificationRecord.user_id == user_id,
                        NotificationRecord.port_id == port_id,
                        NotificationRecord.email_dispatched.is_(True),
                        NotificationRecord.created_at >= cutoff,
                    )
                    .order_by(NotificationRecord.created_at.desc())
                    .first()
                )
                if recent and recent.created_at:
                    ts = (
                        recent.created_at.timestamp()
                        if recent.created_at.tzinfo
                        else recent.created_at.replace(tzinfo=timezone.utc).timestamp()
                    )
                    self._last_email_sent[(uid, pid)] = ts
                    return (now - ts) < self.EMAIL_COOLDOWN_SECONDS
        except Exception:
            pass

        return False

    def record_email_sent(
        self, user_id: str, port_id: str, timestamp: Optional[float] = None
    ) -> None:
        """Record that an email was dispatched for (user_id, port_id) to start or reset the 30-minute cooldown."""
        uid = user_id.strip().lower()
        pid = port_id.strip().lower()
        ts = timestamp if timestamp is not None else time.time()
        self._last_email_sent[(uid, pid)] = ts

    def clear_cooldown(
        self, user_id: Optional[str] = None, port_id: Optional[str] = None
    ) -> None:
        """Clear email cooldown records (useful for testing and administrative resets)."""
        if user_id is not None and port_id is not None:
            self._last_email_sent.pop((user_id.strip().lower(), port_id.strip().lower()), None)
        elif user_id is not None:
            uid = user_id.strip().lower()
            keys_to_del = [k for k in self._last_email_sent if k[0] == uid]
            for k in keys_to_del:
                del self._last_email_sent[k]
        else:
            self._last_email_sent.clear()

    async def get_notifications(
        self, user_id: str, unread_only: bool = False
    ) -> List[Notification]:
        """Retrieve user notifications in reverse chronological order from the database."""
        with get_db_context() as db:
            query = db.query(NotificationRecord).filter(NotificationRecord.user_id == user_id)
            if unread_only:
                query = query.filter(NotificationRecord.read.is_(False))

            records = (
                query.order_by(NotificationRecord.created_at.desc(), NotificationRecord.id.desc())
                .all()
            )
            return [r.to_pydantic() for r in records]

    async def mark_as_read(self, notification_id: str, user_id: str) -> Notification:
        """Mark a specific notification as read in the database."""
        with get_db_context() as db:
            record = (
                db.query(NotificationRecord)
                .filter(
                    NotificationRecord.id == notification_id,
                    NotificationRecord.user_id == user_id,
                )
                .first()
            )
            if not record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Notification with ID '{notification_id}' not found.",
                )

            record.read = True
            db.commit()
            db.refresh(record)
            return record.to_pydantic()

    async def mark_all_as_read(self, user_id: str) -> None:
        """Mark all notifications for this user as read in the database."""
        with get_db_context() as db:
            db.query(NotificationRecord).filter(
                NotificationRecord.user_id == user_id,
                NotificationRecord.read.is_(False),
            ).update({"read": True}, synchronize_session=False)
            db.commit()

    async def create_alert(
        self, alert_req: CreateAlertRequest, user_id: str
    ) -> Notification:
        """Create a state-change alert notification persisted to the database."""
        notif_id = f"notif-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        now_str = datetime.now(timezone.utc).isoformat()

        new_label = TIER_LABELS.get(alert_req.newTier, alert_req.newTier.capitalize())
        prev_label = (
            TIER_LABELS.get(alert_req.previousTier, alert_req.previousTier.capitalize())
            if alert_req.previousTier
            else None
        )

        title = f"{alert_req.portName}: Risk tier changed to {new_label}"
        message = (
            f"{alert_req.portName} risk status shifted from {prev_label} to {new_label}."
            if prev_label
            else f"{alert_req.portName} initial risk assessment: {new_label}."
        )

        # Check if user has opted out of notifications for this port in the database
        port_notifications_enabled = True
        vessel_label: Optional[str] = None
        monitored_port_id: Optional[str] = None
        with get_db_context() as db:
            monitored_port = (
                db.query(MonitoredPort)
                .filter(
                    (MonitoredPort.id == alert_req.portId) | (MonitoredPort.locode == alert_req.portId.upper()),
                    MonitoredPort.user_id == user_id,
                )
                .first()
            )
            if monitored_port:
                monitored_port_id = monitored_port.id
                if not monitored_port.notifications_enabled:
                    port_notifications_enabled = False
                if monitored_port.vessel_class:
                    from app.services.risk_service import VESSEL_CLASS_METADATA
                    vessel_label = VESSEL_CLASS_METADATA.get(monitored_port.vessel_class, {}).get("label")

            if vessel_label:
                title = f"{alert_req.portName} ({vessel_label}): Risk tier changed to {new_label}"
                message = (
                    f"{alert_req.portName} ({vessel_label}) risk status shifted from {prev_label} to {new_label}."
                    if prev_label
                    else f"{alert_req.portName} ({vessel_label}) initial risk assessment: {new_label}."
                )

            recipient_email = None
            if port_notifications_enabled:
                recipient_email = user_id if "@" in user_id else f"{user_id}@berthmark.com"

            # Check outbound email suppression:
            # 1. AISStream initial warm-up suppression (stream data ramping up from cold start)
            # 2. 30-minute cooldown suppression per user and port
            should_dispatch_email = False
            effective_port_id = monitored_port_id or alert_req.portId

            if recipient_email:
                is_warmup = False
                try:
                    from app.clients.ais_stream_manager import get_stream_manager
                    stream_mgr = get_stream_manager()
                    if stream_mgr and stream_mgr.is_warming_up:
                        is_warmup = True
                except Exception:
                    pass

                in_cooldown = self.is_email_cooldown_active(user_id, effective_port_id)
                if not in_cooldown and alert_req.portId != effective_port_id:
                    in_cooldown = self.is_email_cooldown_active(user_id, alert_req.portId)

                if is_warmup:
                    logger.info(
                        "Warning email suppressed for %s on %s: AISStream warm-up active",
                        recipient_email,
                        effective_port_id,
                    )
                elif in_cooldown:
                    logger.info(
                        "Warning email suppressed for %s on %s: 30-minute cooldown active",
                        recipient_email,
                        effective_port_id,
                    )
                else:
                    should_dispatch_email = True

            record = NotificationRecord(
                id=notif_id,
                user_id=user_id,
                type="stateChange",
                port_id=alert_req.portId,
                port_name=alert_req.portName,
                title=title,
                message=message,
                tier=alert_req.newTier,
                previous_tier=alert_req.previousTier,
                timestamp=now_str,
                read=False,
                recipient_email=recipient_email,
                email_dispatched=should_dispatch_email,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            notification = record.to_pydantic()

        # Dispatch email if eligible
        if should_dispatch_email and recipient_email:
            try:
                from app.services.email_service import email_service
                vessel_line = f"Vessel Class: {vessel_label}\n" if vessel_label else ""
                email_body = (
                    f"Operational Alert: Risk State Transition\n\n"
                    f"Port: {alert_req.portName}\n"
                    f"{vessel_line}"
                    f"Alert: {message}\n"
                    f"New Risk Tier: {new_label}\n"
                    f"Previous Tier: {prev_label or 'None'}\n"
                    f"Timestamp: {now_str}\n\n"
                    f"Destination: {recipient_email}\n"
                    f"To adjust your notification preferences, visit your Berthmark dashboard.\n"
                )
                subject_vessel = f" [{vessel_label}]" if vessel_label else ""
                await email_service.send_email(
                    to_email=recipient_email,
                    subject=f"[Berthmark Alert] {alert_req.portName}{subject_vessel}: Risk shifted to {new_label}",
                    plain_text=email_body,
                )
                self.record_email_sent(user_id, effective_port_id)
                if alert_req.portId != effective_port_id:
                    self.record_email_sent(user_id, alert_req.portId)
            except Exception as e:
                logger.warning("Failed to dispatch alert email to %s: %s", recipient_email, e)

        return notification

    async def send_subscription_baseline_email(
        self, port, user_id: str
    ) -> Notification:
        """Evaluate baseline risk and send an immediate welcome & baseline risk alert email upon subscription."""
        recipient_email = user_id if "@" in user_id else f"{user_id}@berthmark.com"
        now_str = datetime.now(timezone.utc).isoformat()
        notif_id = f"notif-{int(time.time())}-{uuid.uuid4().hex[:6]}"

        vessel_class = getattr(port, "vesselClass", None) or getattr(port, "vessel_class", None) or "neoPanamax"
        from app.services.risk_service import VESSEL_CLASS_METADATA
        vessel_label = VESSEL_CLASS_METADATA.get(vessel_class, {}).get("label", vessel_class)

        tier: RiskTier = "low"
        score = 25.0
        wind_speed = 0.0
        wave_height = 0.0
        queue_count = 0
        active_vessels = 0
        channel_depth = port.channelDepthM or 0.0

        try:
            from app.services.risk_service import risk_service
            assessment = await risk_service.get_risk_assessment(
                port_id=port.id,
                port_name=port.name,
                vessel_class=vessel_class,
                user_id=user_id,
            )
            tier = assessment.compositeTier
            score = assessment.compositeScore
            wind_speed = assessment.metrics.weather.windSpeedKnots
            wave_height = assessment.metrics.weather.waveHeightM
            queue_count = assessment.metrics.congestion.anchorageQueueCount
            active_vessels = assessment.metrics.congestion.activeVesselCount
            channel_depth = assessment.metrics.navigational.channelDepthM
        except Exception:
            pass

        tier_label = TIER_LABELS.get(tier, tier.capitalize())
        title = f"{port.name} ({vessel_label}): Subscribed (Baseline Risk: {tier_label})"
        message = (
            f"Successfully subscribed to {vessel_label} alerts for {port.name} [{port.locode}]. "
            f"Current baseline risk: {tier_label} (Score: {score:.1f}/100, "
            f"Wind: {wind_speed:.1f} kts, Waves: {wave_height:.1f}m, "
            f"Anchorage Queue: {queue_count} vessels, Channel Depth: {channel_depth:.1f}m). "
            f"Alerts active for {recipient_email}."
        )

        with get_db_context() as db:
            record = NotificationRecord(
                id=notif_id,
                user_id=user_id,
                type="stateChange",
                port_id=port.id,
                port_name=port.name,
                title=title,
                message=message,
                tier=tier,
                previous_tier=None,
                timestamp=now_str,
                read=False,
                recipient_email=recipient_email,
                email_dispatched=True,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            notification = record.to_pydantic()

        # Dispatch email
        email_body = (
            f"Welcome to Berthmark Port-Call Risk Tracker!\n\n"
            f"You have subscribed to automated operational & weather alerts for:\n"
            f"  Port: {port.name} [{port.locode}] - {port.country}\n"
            f"  Vessel Class: {vessel_label}\n"
            f"  Destination: {recipient_email}\n\n"
            f"CURRENT LIVE BASELINE CONDITIONS:\n"
            f"  • Composite Risk Tier: {tier_label} (Score: {score:.1f}/100)\n"
            f"  • Wind Speed: {wind_speed:.1f} knots\n"
            f"  • Significant Wave Height: {wave_height:.1f} meters\n"
            f"  • Anchorage Waiting Queue: {queue_count} vessels ({active_vessels} total active in geofence)\n"
            f"  • Controlling Channel Depth (NGA WPI): {channel_depth:.1f}m\n\n"
            f"You will automatically receive an email alert whenever weather or traffic triggers a risk state transition.\n"
            f"You can opt out per-port at any time in your Monitored Ports portfolio.\n"
        )
        try:
            from app.services.email_service import email_service
            await email_service.send_email(
                to_email=recipient_email,
                subject=f"[Berthmark Alert] Subscribed to {port.name} [{vessel_label}] (Baseline Risk: {tier_label})",
                plain_text=email_body,
            )
            # Record that an outbound email was dispatched, starting the 30-minute cooldown
            self.record_email_sent(user_id, port.id)
            if hasattr(port, "locode") and port.locode:
                self.record_email_sent(user_id, port.locode)
        except Exception as e:
            logger.warning("Failed to dispatch subscription baseline email to %s: %s", recipient_email, e)

        return notification


notification_service = NotificationService()
