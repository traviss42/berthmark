"""FastAPI router for Notification feed and alert management endpoints (Issue 18)."""

import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.auth.schemas import ErrorResponse
from backend.database import get_db_session
from backend.models import User
from backend.schemas.notification import Notification, NotificationCreate
from backend.services.notification_service import (
    create_state_change_alert,
    get_user_notifications,
    mark_all_notifications_as_read,
    mark_notification_as_read,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get(
    "",
    response_model=list[Notification],
    summary="Get notifications for the authenticated user",
    responses={
        200: {"description": "Notification feed list.", "model": list[Notification]},
        400: {"description": "Invalid query parameters.", "model": ErrorResponse},
        401: {"description": "Unauthorized.", "model": ErrorResponse},
        500: {"description": "Internal server error.", "model": ErrorResponse},
    },
)
async def list_notifications(
    unreadOnly: bool = Query(False, description="Filter only unread notifications."),
    limit: int = Query(50, description="Maximum notifications to return."),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[Notification]:
    """Retrieve notifications feed for authenticated user with reverse-chronological ordering."""
    if not (1 <= limit <= 100):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Bad Request",
                "message": f"Query parameter 'limit' must be between 1 and 100, got {limit}.",
                "statusCode": 400,
            },
        )

    try:
        return await get_user_notifications(
            session=session,
            user_id=current_user.id,
            unread_only=unreadOnly,
            limit=limit,
        )
    except Exception as exc:
        logger.exception("Failed to retrieve notifications for user %s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal Server Error",
                "message": f"Failed to retrieve notifications: {str(exc)}",
                "statusCode": 500,
            },
        )


@router.post(
    "",
    response_model=Notification,
    status_code=status.HTTP_201_CREATED,
    summary="Create or trigger a risk state-change alert",
    responses={
        201: {"description": "Notification created successfully.", "model": Notification},
        400: {"description": "Invalid payload parameters.", "model": ErrorResponse},
        401: {"description": "Unauthorized.", "model": ErrorResponse},
        500: {"description": "Internal server error.", "model": ErrorResponse},
    },
)
async def create_notification(
    payload: NotificationCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Notification:
    """Create a new state-change notification alert for the authenticated user."""
    try:
        return await create_state_change_alert(
            session=session,
            user_id=current_user.id,
            payload=payload,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Bad Request",
                "message": str(exc),
                "statusCode": 400,
            },
        )
    except Exception as exc:
        logger.exception("Failed to create notification alert: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal Server Error",
                "message": f"Failed to create notification alert: {str(exc)}",
                "statusCode": 500,
            },
        )


@router.patch(
    "/{notificationId}/read",
    response_model=Notification,
    summary="Mark notification as read",
    responses={
        200: {"description": "Notification marked as read.", "model": Notification},
        401: {"description": "Unauthorized.", "model": ErrorResponse},
        404: {"description": "Notification not found.", "model": ErrorResponse},
        500: {"description": "Internal server error.", "model": ErrorResponse},
    },
)
async def mark_single_read(
    notificationId: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Notification:
    """Update a specific notification's status to read=true with multi-tenant ownership check."""
    try:
        updated = await mark_notification_as_read(
            session=session,
            user_id=current_user.id,
            notification_id=notificationId,
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "Not Found",
                    "message": f"Notification '{notificationId}' not found.",
                    "statusCode": 404,
                },
            )
        return updated
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to mark notification %s as read: %s", notificationId, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal Server Error",
                "message": f"Failed to update notification: {str(exc)}",
                "statusCode": 500,
            },
        )


@router.post(
    "/mark-all-read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark all user notifications as read",
    responses={
        204: {"description": "All notifications marked as read."},
        401: {"description": "Unauthorized.", "model": ErrorResponse},
        500: {"description": "Internal server error.", "model": ErrorResponse},
    },
)
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Mark all unread notifications for the authenticated user as read."""
    try:
        await mark_all_notifications_as_read(session=session, user_id=current_user.id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:
        logger.exception("Failed to mark all notifications as read for user %s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal Server Error",
                "message": f"Failed to mark all notifications as read: {str(exc)}",
                "statusCode": 500,
            },
        )
