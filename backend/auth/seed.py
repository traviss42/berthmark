"""Default operator credentials seeder."""

import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.auth.security import hash_password
from backend.models import User

DEFAULT_OPERATOR_EMAIL = "operator@maritimerisk.com"
DEFAULT_OPERATOR_PASSWORD = "SampleSecurePassword123!"
DEFAULT_OPERATOR_NAME = "Ship Operations Manager"


async def seed_default_user(session: AsyncSession) -> User:
    """Idempotently seed the default ship operations manager user."""
    result = await session.execute(
        select(User).where(func.lower(User.email) == DEFAULT_OPERATOR_EMAIL.lower())
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            id=uuid.uuid4(),
            email=DEFAULT_OPERATOR_EMAIL,
            hashed_password=hash_password(DEFAULT_OPERATOR_PASSWORD),
            name=DEFAULT_OPERATOR_NAME,
        )
        session.add(user)
    else:
        user.hashed_password = hash_password(DEFAULT_OPERATOR_PASSWORD)
        user.name = DEFAULT_OPERATOR_NAME

    await session.commit()
    await session.refresh(user)
    return user
