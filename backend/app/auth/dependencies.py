"""Authentication dependencies using HTTPBearer with Supabase/JWT or token decoding."""

import base64
import json
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Security scheme
security_required = HTTPBearer(auto_error=False)
security_optional = HTTPBearer(auto_error=False)


def _extract_user_id_from_token(token: str) -> str:
    """Extract user identifier from token (supports raw user ID, test tokens, or JWTs)."""
    token = token.strip()
    if not token:
        raise ValueError("Token is empty")

    # If it is a JWT token (3 base64url segments separated by dots)
    segments = token.split(".")
    if len(segments) == 3:
        try:
            payload_segment = segments[1]
            # Add padding
            rem = len(payload_segment) % 4
            if rem > 0:
                payload_segment += "=" * (4 - rem)
            decoded = base64.urlsafe_b64decode(payload_segment.encode("utf-8"))
            data = json.loads(decoded.decode("utf-8"))
            user_id = data.get("sub") or data.get("user_id") or data.get("email")
            if user_id:
                return str(user_id)
        except Exception:
            pass

    # Otherwise treat the token string directly as user identifier (e.g. "mock-user", "user-123")
    return token


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_required),
) -> str:
    """Enforce authentication and return the authenticated user ID."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = _extract_user_id_from_token(credentials.credentials)
        return user_id
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
) -> Optional[str]:
    """Optionally resolve user if Authorization header is provided."""
    if not credentials or not credentials.credentials:
        return None
    try:
        return _extract_user_id_from_token(credentials.credentials)
    except Exception:
        return None
