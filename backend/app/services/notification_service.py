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

        return notification


notification_service = NotificationService()
