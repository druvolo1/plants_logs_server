# app/dependencies.py
"""
Common dependency functions for FastAPI routes.
"""
from typing import Optional
from fastapi import Depends, Header, HTTPException, Request
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
    request: Request,
    session: AsyncSession = Depends(get_db_dependency())
) -> Optional[User]:
    """
    Get current user if authenticated, None otherwise.
    Used for endpoints that work with or without authentication (e.g., public discovery).
    Checks both cookies and Authorization header.
    """
    import jwt
    from sqlalchemy import select

    # Import here to avoid circular dependency
    from app.main import SECRET

    # Try to get auth from cookie first
    cookie = request.cookies.get("auth_cookie")
    if cookie:
        try:
            payload = jwt.decode(cookie, SECRET, algorithms=["HS256"], options={"verify_aud": False})
            user_id = payload.get("sub")
            if user_id:
                result = await session.execute(select(User).where(User.id == int(user_id)))
                user = result.scalars().first()
                if user:
                    return user
        except:
            pass

    # Try Authorization header as fallback
    auth_header = request.headers.get("authorization")
    if auth_header:
        try:
            current_user_dep = get_current_user_dependency()
            user = await current_user_dep(request)
            return user
        except:
            pass

    return None


async def require_superuser(
    current_user: User = Depends(get_current_user_dependency())
) -> User:
    """
    Dependency that ensures the current user is a superuser.
    Raises 403 if not a superuser.
    """
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser access required")
    return current_user
