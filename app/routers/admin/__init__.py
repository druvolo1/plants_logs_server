# app/routers/admin/__init__.py
"""
Admin router package - modular admin endpoints.

This package contains:
- dashboard: Dashboard page and stats API
- users: User management endpoints
- devices: Device management and data viewing
- database: Data retention and legacy log management
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import User

# Create main admin router
router = APIRouter(prefix="/admin", tags=["admin"])


def get_current_admin_dependency():
    """Import and return current_admin dependency"""
    from app.main import current_admin
    return current_admin


def get_db_dependency():
    """Import and return get_db dependency"""
    from app.main import get_db
    return get_db


def get_user_manager_dependency():
    """Import and return get_user_manager dependency"""
    from app.main import get_user_manager
    return get_user_manager


def get_templates():
    """Import and return templates"""
    from app.main import templates
    return templates


# Main dashboard page (registered directly on admin router to avoid empty path issue)
@router.get("", response_class=HTMLResponse)
async def admin_dashboard_page(
    request: Request,
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Admin dashboard page"""
    pending_result = await session.execute(
        select(func.count(User.id)).where(User.is_active == False)
    )
    pending_count = pending_result.scalar() or 0

    return get_templates().TemplateResponse("admin_dashboard.html", {
        "request": request,
        "user": admin,
        "active_page": "dashboard",
        "pending_users_count": pending_count
    })


# Import and include sub-routers
from app.routers.admin.dashboard import router as dashboard_router
from app.routers.admin.users import router as users_router
from app.routers.admin.devices import router as devices_router
from app.routers.admin.database import router as database_router

router.include_router(dashboard_router)
router.include_router(users_router)
router.include_router(devices_router)
router.include_router(database_router)
