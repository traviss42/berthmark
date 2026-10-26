"""FastAPI router for user authentication and profile endpoints."""

import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.dependencies import get_current_user
from backend.auth.schemas import (
    AuthResponse,
    ErrorResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from backend.auth.security import create_access_token, hash_password, verify_password
from backend.database import get_db_session
from backend.models import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])


@router.post(
    "/auth/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="User registration",
    responses={
        201: {"description": "User registered successfully.", "model": AuthResponse},
        400: {"description": "Bad Request.", "model": ErrorResponse},
        409: {"description": "Email already registered.", "model": ErrorResponse},
        500: {"description": "Internal server error.", "model": ErrorResponse},
    },
)
async def register(
    reg_req: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    """Register a new user, securely hash the password, and issue a signed JWT access token."""
    normalized_email = reg_req.email.lower().strip()
    if not normalized_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Bad Request",
                "message": "Email is required.",
                "statusCode": 400,
            },
        )

    clean_password = reg_req.password.strip()
    if not clean_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Bad Request",
                "message": "Password cannot be empty.",
                "statusCode": 400,
            },
        )

    # Check if user with this email already exists
    try:
        result = await session.execute(
            select(User).where(func.lower(User.email) == normalized_email)
        )
        existing = result.scalar_one_or_none()
    except Exception as exc:
        logger.exception("Database error while checking user registration: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal Server Error",
                "message": "Database query failed during registration check.",
                "statusCode": 500,
            },
        )

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "Conflict",
                "message": f"User with email '{normalized_email}' is already registered.",
                "statusCode": 409,
            },
        )

    hashed_pw = hash_password(clean_password)
    user_name = reg_req.name.strip() if reg_req.name and reg_req.name.strip() else None

    new_user = User(
        id=uuid.uuid4(),
        email=normalized_email,
        hashed_password=hashed_pw,
        name=user_name,
    )

    try:
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
    except Exception as exc:
        logger.exception("Database error while creating user record: %s", exc)
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal Server Error",
                "message": "Failed to create user record.",
                "statusCode": 500,
            },
        )

    token, expires_in = create_access_token({
        "sub": str(new_user.id),
        "email": new_user.email,
    })

    return AuthResponse(
        accessToken=token,
        tokenType="Bearer",
        expiresIn=expires_in,
        user=UserResponse(
            id=str(new_user.id),
            email=new_user.email,
            name=new_user.name,
            createdAt=new_user.created_at.isoformat(),
        ),
    )


@router.post(
    "/auth/login",
    response_model=AuthResponse,
    summary="User login",
    responses={
        200: {"description": "Login successful.", "model": AuthResponse},
        401: {"description": "Invalid credentials.", "model": ErrorResponse},
        500: {"description": "Internal server error.", "model": ErrorResponse},
    },
)
async def login(
    login_req: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    """Authenticate user credentials and issue signed JWT access token."""
    normalized_email = login_req.email.lower().strip()

    try:
        # Parameterized async query
        result = await session.execute(
            select(User).where(func.lower(User.email) == normalized_email)
        )
        user = result.scalar_one_or_none()
    except Exception as exc:
        logger.exception("Database error during login: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Internal Server Error",
                "message": "Database query failed during authentication.",
                "statusCode": 500,
            },
        )

    # Constant-time comparison or fail gracefully to prevent user enumeration
    if user is None or not verify_password(login_req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "Unauthorized",
                "message": "Invalid credentials.",
                "statusCode": 401,
            },
        )

    # Generate token
    token, expires_in = create_access_token({
        "sub": str(user.id),
        "email": user.email,
    })

    return AuthResponse(
        accessToken=token,
        tokenType="Bearer",
        expiresIn=expires_in,
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
            createdAt=user.created_at.isoformat(),
        ),
    )


@router.get(
    "/auth/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile",
    responses={
        200: {"description": "Authenticated user details.", "model": UserResponse},
        401: {"description": "Authentication token missing or expired.", "model": ErrorResponse},
        500: {"description": "Internal server error.", "model": ErrorResponse},
    },
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Retrieve identity and account profile of authenticated user."""
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        name=current_user.name,
        createdAt=current_user.created_at.isoformat(),
    )
