"""Notification and alert endpoints implementing openapi.yaml specifications."""

from typing import List
from fastapi import APIRouter, Depends, Query, status
from app.auth.dependencies import get_current_user
from app.models.notification import CreateAlertRequest, Notification
from app.services.notification_service import NotificationService, notification_service

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])


@router.get(
    "",
    response_model=List[Notification],
    summary="Get user notifications",
    description="Retrieves in-app alerts and notifications for the authenticated user.",
)
async def get_user_notifications(
    unreadOnly: bool = Query(False, description="Filter for unread notifications only"),
    current_user: str = Depends(get_current_user),
    service: NotificationService = Depends(lambda: notification_service),
) -> List[Notification]:
    return await service.get_notifications(user_id=current_user, unread_only=unreadOnly)


@router.patch(
    "/{notificationId}/read",
    response_model=Notification,
    summary="Mark a single notification as read",
    description="Marks an individual user notification as read.",
)
async def mark_notification_as_read(
    notificationId: str,
    current_user: str = Depends(get_current_user),
    service: NotificationService = Depends(lambda: notification_service),
) -> Notification:
    return await service.mark_as_read(notification_id=notificationId, user_id=current_user)


@router.post(
    "/mark-all-read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark all notifications as read",
    description="Marks all active notifications for the user as read.",
)
async def mark_all_notifications_as_read(
    current_user: str = Depends(get_current_user),
    service: NotificationService = Depends(lambda: notification_service),
) -> None:
    await service.mark_all_as_read(user_id=current_user)


@router.post(
    "/alerts",
    response_model=Notification,
    status_code=status.HTTP_201_CREATED,
    summary="Create or trigger a risk state-change alert",
    description="Creates a state-change notification when a port transitions between risk tiers.",
)
async def create_state_change_alert(
    alert_req: CreateAlertRequest,
    current_user: str = Depends(get_current_user),
    service: NotificationService = Depends(lambda: notification_service),
) -> Notification:
    return await service.create_alert(alert_req=alert_req, user_id=current_user)
