# app/routers/admin/config.py
"""
System configuration endpoints for admin portal.
"""
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from app.models import User

router = APIRouter()


def _get_current_admin():
    from app.main import current_admin
    return current_admin


def _get_db():
    from app.main import get_db
    return get_db


def _get_templates():
    from app.main import templates
    return templates


# Configuration storage (in production, use database or config file)
# For now, storing in memory
system_config = {
    "logging": {
        "posting_window_start_hour": 1,
        "posting_window_end_hour": 6
    }
}


class LoggingConfigUpdate(BaseModel):
    posting_window_start_hour: int
    posting_window_end_hour: int


# HTML Page

@router.get("/config", response_class=HTMLResponse)
async def system_config_page(
    request: Request,
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """System Configuration page"""
    # Count pending users for sidebar badge
    pending_result = await session.execute(
        select(func.count(User.id)).where(User.is_active == False)
    )
    pending_count = pending_result.scalar() or 0

    return _get_templates().TemplateResponse("admin_config.html", {
        "request": request,
        "user": admin,
        "active_page": "config",
        "pending_users_count": pending_count,
        "logging_config": system_config["logging"]
    })


# API Endpoints

@router.get("/config/logging")
async def get_logging_config(
    admin: User = Depends(_get_current_admin())
) -> Dict:
    """Get current logging configuration"""
    return system_config["logging"]


@router.post("/config/logging")
async def update_logging_config(
    config: LoggingConfigUpdate,
    admin: User = Depends(_get_current_admin())
) -> Dict:
    """Update logging configuration"""
    # Validate hours
    if not (0 <= config.posting_window_start_hour <= 23):
        raise HTTPException(400, "Start hour must be between 0 and 23")
    if not (0 <= config.posting_window_end_hour <= 23):
        raise HTTPException(400, "End hour must be between 0 and 23")
    if config.posting_window_start_hour >= config.posting_window_end_hour:
        raise HTTPException(400, "End hour must be after start hour")

    # Update config
    system_config["logging"]["posting_window_start_hour"] = config.posting_window_start_hour
    system_config["logging"]["posting_window_end_hour"] = config.posting_window_end_hour

    print(f"[CONFIG] Admin {admin.email} updated logging window: {config.posting_window_start_hour}:00 - {config.posting_window_end_hour}:00")

    return {
        "status": "success",
        "message": "Logging configuration updated",
        "config": system_config["logging"]
    }
