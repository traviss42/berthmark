"""Notification service managing state-change alerts and multi-tenant feeds (Issue 18)."""

from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import AlertLog, Port
from backend.ports.service import BENCHMARK_PORTS_METADATA
from backend.schemas.notification import Notification, NotificationCreate, NotificationType
from backend.schemas.risk import RiskTier

logger = logging.getLogger(__name__)


def alert_log_to_notification(alert: AlertLog, port_name_override: str | None = None) -> Notification:
    """Map database AlertLog record to OpenAPI Notification schema payload."""
    port_name = port_name_override
    if not port_name:
        port_name = alert.port.port_name if alert.port else alert.unlocode

    canonical_port_id = f"port-{alert.unlocode.lower()}"
    for locode, meta in BENCHMARK_PORTS_METADATA.items():
        if locode.upper() == alert.unlocode.upper():
            canonical_port_id = meta["id"]
            if not port_name_override and "name" in meta:
                port_name = meta["name"]
            break

    raw_tier = (alert.new_risk_level or "LOW").lower()
    raw_prev = alert.previous_risk_level.lower() if alert.previous_risk_level else None

    title = alert.title or f"{port_name}: Risk tier changed to {raw_tier.capitalize()}"
    message = alert.message or alert.trigger_reason

    notif_id = f"notif-{alert.alert_id}"

    # Notification type casting
    notif_type: NotificationType = "stateChange"
    if alert.type in ("stateChange", "dailyDigest", "inApp"):
        notif_type = alert.type  # type: ignore[assignment]

    return Notification(
        id=notif_id,
        type=notif_type,
        portId=canonical_port_id,
        portName=port_name,
        title=title,
        message=message,
        tier=raw_tier,  # type: ignore[arg-type]
        previousTier=raw_prev,  # type: ignore[arg-type]
        timestamp=alert.created_at,
        read=bool(alert.is_read),
    )


async def get_user_notifications(
    session: AsyncSession,
    user_id: uuid.UUID,
    unread_only: bool = False,
    limit: int = 50,
) -> list[Notification]:
    """Retrieve reverse-chronological notification alerts with multi-tenant user isolation."""
    if not (1 <= limit <= 100):
        raise ValueError(f"Limit must be between 1 and 100, got {limit}")

    stmt = (
        select(AlertLog)
        .options(selectinload(AlertLog.port))
        .where(AlertLog.user_id == user_id)
    )

    if unread_only:
        stmt = stmt.where(AlertLog.is_read.is_(False))

    stmt = stmt.order_by(AlertLog.created_at.desc()).limit(limit)

    res = await session.execute(stmt)
    alerts = list(res.scalars().all())

    return [alert_log_to_notification(a) for a in alerts]


async def create_state_change_alert(
    session: AsyncSession,
    user_id: uuid.UUID,
    payload: NotificationCreate,
) -> Notification:
    """Explicitly create and persist a new state-change alert for the authenticated user."""
    # Resolve port LOCODE
    clean_id = payload.portId.strip()
    locode_match = None
    for locode, meta in BENCHMARK_PORTS_METADATA.items():
        if meta["id"].lower() == clean_id.lower() or locode.lower() == clean_id.lower():
            locode_match = locode.upper()
            break
    if not locode_match:
        locode_match = clean_id[5:].upper() if clean_id.lower().startswith("port-") else clean_id.upper()

    # Verify port exists in DB or benchmark metadata
    p_stmt = select(Port).where(Port.unlocode == locode_match)
    p_res = await session.execute(p_stmt)
    port = p_res.scalar_one_or_none()
    if not port and locode_match in BENCHMARK_PORTS_METADATA:
        meta = BENCHMARK_PORTS_METADATA[locode_match]
        port = Port(
            unlocode=meta["locode"],
            port_name=meta["name"],
            country_code=meta["country"],
            subdivision_code=meta["subdivision"],
            latitude=meta["lat"],
            longitude=meta["lon"],
            channel_depth_m=meta.get("channelDepthM"),
            is_depth_available=True,
            reconciliation_method="EXACT_UNLOCODE",
        )
        session.add(port)
        await session.flush()
    elif not port:
        # Fallback create placeholder port to satisfy foreign key
        port = Port(
            unlocode=locode_match,
            port_name=payload.portName,
            country_code="UN",
            subdivision_code="UN-00",
            latitude=0.0,
            longitude=0.0,
            channel_depth_m=15.0,
            is_depth_available=True,
            reconciliation_method="EXACT_UNLOCODE",
        )
        session.add(port)
        await session.flush()

    new_tier_upper = payload.newTier.upper()
    prev_tier_upper = payload.previousTier.upper() if payload.previousTier else None

    title = f"{payload.portName}: Risk tier changed to {payload.newTier.capitalize()}"
    prev_label = payload.previousTier.capitalize() if payload.previousTier else "None"
    message = f"{payload.portName} risk status shifted from {prev_label} to {payload.newTier.capitalize()}."

    alert = AlertLog(
        alert_id=uuid.uuid4(),
        user_id=user_id,
        unlocode=port.unlocode,
        vessel_class_id="neoPanamax",
        type=payload.type,
        title=title,
        message=message,
        previous_risk_level=prev_tier_upper,
        new_risk_level=new_tier_upper,
        trigger_reason=message,
        is_read=False,
        created_at=datetime.now(timezone.utc),
    )
    session.add(alert)
    await session.flush()

    return alert_log_to_notification(alert, port_name_override=payload.portName)


async def mark_notification_as_read(
    session: AsyncSession,
    user_id: uuid.UUID,
    notification_id: str,
) -> Notification | None:
    """Mark a specific user notification as read with strict multi-tenant isolation."""
    clean_id = notification_id.strip()
    if clean_id.startswith("notif-"):
        clean_id = clean_id[6:]

    try:
        alert_uuid = uuid.UUID(clean_id)
    except ValueError:
        return None

    stmt = (
        select(AlertLog)
        .options(selectinload(AlertLog.port))
        .where(
            AlertLog.alert_id == alert_uuid,
            AlertLog.user_id == user_id,
        )
    )
    res = await session.execute(stmt)
    alert = res.scalar_one_or_none()
    if not alert:
        return None

    alert.is_read = True
    await session.flush()

    return alert_log_to_notification(alert)


async def mark_all_notifications_as_read(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> int:
    """Mark all unread notifications for the authenticated user as read."""
    stmt = (
        update(AlertLog)
        .where(
            AlertLog.user_id == user_id,
            AlertLog.is_read.is_(False),
        )
        .values(is_read=True)
    )
    res = await session.execute(stmt)
    await session.flush()
    return res.rowcount  # type: ignore[return-value]
