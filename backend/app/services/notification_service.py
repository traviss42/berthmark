"""Notification service managing in-app alerts and risk state transitions with database persistence."""

import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import HTTPException, status
from app.db.models import MonitoredPort, NotificationRecord
from app.db.session import get_db_context
from app.models.common import RiskTier
from app.models.notification import CreateAlertRequest, Notification

TIER_LABELS: Dict[RiskTier, str] = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
}


class NotificationService:
    """Manages user alerts, state-change triggers, and read status backed by SQLAlchemy database."""

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
        with get_db_context() as db:
            monitored_port = (
                db.query(MonitoredPort)
                .filter(
                    MonitoredPort.id == alert_req.portId,
                    MonitoredPort.user_id == user_id,
                )
                .first()
            )
            if monitored_port and not monitored_port.notifications_enabled:
                port_notifications_enabled = False

            recipient_email = None
            if port_notifications_enabled:
                recipient_email = user_id if "@" in user_id else f"{user_id}@berthmark.com"

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
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            notification = record.to_pydantic()

        # Dispatch email if recipient is enabled
        if recipient_email:
            try:
                from app.services.email_service import email_service
                email_body = (
                    f"Operational Alert: Risk State Transition\n\n"
                    f"Port: {alert_req.portName}\n"
                    f"Alert: {message}\n"
                    f"New Risk Tier: {new_label}\n"
                    f"Previous Tier: {prev_label or 'None'}\n"
                    f"Timestamp: {now_str}\n\n"
                    f"Destination: {recipient_email}\n"
                    f"To adjust your notification preferences, visit your Berthmark dashboard.\n"
                )
                await email_service.send_email(
                    to_email=recipient_email,
                    subject=f"[Berthmark Alert] {alert_req.portName}: Risk shifted to {new_label}",
                    plain_text=email_body,
                )
            except Exception:
                pass

        return notification

    async def send_subscription_baseline_email(
        self, port, user_id: str
    ) -> Notification:
        """Evaluate baseline risk and send an immediate welcome & baseline risk alert email upon subscription."""
        recipient_email = user_id if "@" in user_id else f"{user_id}@berthmark.com"
        now_str = datetime.now(timezone.utc).isoformat()
        notif_id = f"notif-{int(time.time())}-{uuid.uuid4().hex[:6]}"

        tier: RiskTier = "low"
        score = 25.0
        wind_speed = 0.0
        wave_height = 0.0
        queue_count = 0
        berth_occupancy = 60.0

        try:
            from app.services.risk_service import risk_service
            assessment = await risk_service.get_risk_assessment(
                port_id=port.id,
                port_name=port.name,
                vessel_class="neoPanamax",
                user_id=user_id,
            )
            tier = assessment.compositeTier
            score = assessment.compositeScore
            wind_speed = assessment.metrics.weather.windSpeedKnots
            wave_height = assessment.metrics.weather.waveHeightMeters
            queue_count = assessment.metrics.congestion.anchorageQueueCount
            berth_occupancy = assessment.metrics.congestion.berthOccupancyPct
        except Exception:
            pass

        tier_label = TIER_LABELS.get(tier, tier.capitalize())
        title = f"{port.name}: Subscribed (Baseline Risk: {tier_label})"
        message = (
            f"Successfully subscribed to alerts for {port.name} [{port.locode}]. "
            f"Current baseline risk: {tier_label} (Score: {score:.1f}/100, "
            f"Wind: {wind_speed:.1f} kts, Waves: {wave_height:.1f}m, "
            f"Anchorage Queue: {queue_count} vessels, Berth Occupancy: {berth_occupancy:.1f}%). "
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
            f"  Destination: {recipient_email}\n\n"
            f"CURRENT LIVE BASELINE CONDITIONS:\n"
            f"  • Composite Risk Tier: {tier_label} (Score: {score:.1f}/100)\n"
            f"  • Wind Speed: {wind_speed:.1f} knots\n"
            f"  • Significant Wave Height: {wave_height:.1f} meters\n"
            f"  • Anchorage Waiting Queue: {queue_count} vessels\n"
            f"  • Berth Occupancy: {berth_occupancy:.1f}%\n\n"
            f"You will automatically receive an email alert whenever weather or traffic triggers a risk state transition.\n"
            f"You can opt out per-port at any time in your Monitored Ports portfolio.\n"
        )
        try:
            from app.services.email_service import email_service
            await email_service.send_email(
                to_email=recipient_email,
                subject=f"[Berthmark Alert] Subscribed to {port.name} (Baseline Risk: {tier_label})",
                plain_text=email_body,
            )
        except Exception:
            pass

        return notification


notification_service = NotificationService()
