"""FastAPI authentication dependencies for Bearer token validation."""

import uuid
import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.security import decode_access_token
from backend.database import get_db_session
from backend.models import User


async def get_current_user(
    authorization: str | None = Header(None, alias="Authorization"),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """Validate Bearer token from Authorization header and return authenticated User."""
    unauthorized_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": "Unauthorized",
            "message": "Authentication token missing or expired.",
            "statusCode": 401,
        },
    )

    if not authorization:
        raise unauthorized_exc

    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise unauthorized_exc

    token = parts[1]

    try:
        payload = decode_access_token(token)
    except (jwt.PyJWTError, Exception):
        raise unauthorized_exc

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise unauthorized_exc

    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise unauthorized_exc

    result = await session.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None:
        raise unauthorized_exc

    return user
