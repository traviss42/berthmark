"""Notification service managing in-app alerts and risk state transitions."""

import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import HTTPException, status
from app.models.common import RiskTier
from app.models.notification import CreateAlertRequest, Notification

TIER_LABELS: Dict[RiskTier, str] = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
}


class NotificationService:
    """Manages user alerts, state-change triggers, and read status."""

    def __init__(self):
        # user_id -> List[Notification]
        self._user_notifications: Dict[str, List[Notification]] = {}

    async def get_notifications(
        self, user_id: str, unread_only: bool = False
    ) -> List[Notification]:
        """Retrieve user notifications in reverse chronological order."""
        notifs = self._user_notifications.get(user_id, [])
        if unread_only:
            notifs = [n for n in notifs if not n.read]
        # Return newest first
        return list(reversed(notifs))

    async def mark_as_read(self, notification_id: str, user_id: str) -> Notification:
        """Mark a specific notification as read."""
        notifs = self._user_notifications.get(user_id, [])
        for n in notifs:
            if n.id == notification_id:
                n.read = True
                return n

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification with ID '{notification_id}' not found.",
        )

    async def mark_all_as_read(self, user_id: str) -> None:
        """Mark all notifications for this user as read."""
        notifs = self._user_notifications.get(user_id, [])
        for n in notifs:
            n.read = True

    async def create_alert(
        self, alert_req: CreateAlertRequest, user_id: str
    ) -> Notification:
        """Create a state-change alert notification."""
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

        # Check if user has opted out of notifications for this port
        port_notifications_enabled = True
        try:
            from app.services.port_service import port_service
            user_ports = port_service._user_ports.get(user_id, {})
            monitored_port = user_ports.get(alert_req.portId)
            if monitored_port and not monitored_port.notificationsEnabled:
                port_notifications_enabled = False
        except Exception:
            pass

        recipient_email = None
        if port_notifications_enabled:
            recipient_email = user_id if "@" in user_id else f"{user_id}@berthmark.com"

        notification = Notification(
            id=notif_id,
            type="stateChange",
            portId=alert_req.portId,
            portName=alert_req.portName,
            title=title,
            message=message,
            tier=alert_req.newTier,
            previousTier=alert_req.previousTier,
            timestamp=now_str,
            read=False,
            recipientEmail=recipient_email,
        )

        if user_id not in self._user_notifications:
            self._user_notifications[user_id] = []
        self._user_notifications[user_id].append(notification)

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

        notification = Notification(
            id=notif_id,
            type="stateChange",
            portId=port.id,
            portName=port.name,
            title=title,
            message=message,
            tier=tier,
            previousTier=None,
            timestamp=now_str,
            read=False,
            recipientEmail=recipient_email,
        )

        if user_id not in self._user_notifications:
            self._user_notifications[user_id] = []
        self._user_notifications[user_id].append(notification)

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
