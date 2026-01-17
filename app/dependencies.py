# app/dependencies.py
"""
Common dependency functions for FastAPI routes.
"""
from typing import Optional
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import User


def get_current_user_dependency():
    """Import and return current_user dependency from main"""
    from app.main import current_user
    return current_user


def get_db_dependency():
    """Import and return get_db dependency from main"""
    from app.main import get_db
    return get_db


async def get_optional_user(
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_dependency())
) -> Optional[User]:
    """
    Get current user if authenticated, None otherwise.
    Used for endpoints that work with or without authentication (e.g., public discovery).
    """
    if not authorization:
        return None

    try:
        # Get the current_user dependency and call it
        current_user_dep = get_current_user_dependency()
        user = await current_user_dep(authorization, session)
        return user
    except:
        return None


def require_superuser_dependency():
    """Import and return require_superuser dependency from main"""
    from app.main import require_superuser
    return require_superuser
