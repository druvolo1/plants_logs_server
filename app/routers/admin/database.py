# app/routers/admin/database.py
"""
Database management, data retention, and legacy log management endpoints.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete

from app.models import User, Device, Plant, PlantDailyLog, PlantReport
from app.services.data_retention import get_purge_candidates, purge_old_data

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


# HTML Page

@router.get("/database", response_class=HTMLResponse)
async def admin_database_page(
    request: Request,
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Admin database management page"""
    # Count pending users for sidebar badge
    pending_result = await session.execute(
        select(func.count(User.id)).where(User.is_active == False)
    )
    pending_count = pending_result.scalar() or 0

    return _get_templates().TemplateResponse("admin_database.html", {
        "request": request,
        "user": admin,
        "active_page": "database",
        "pending_users_count": pending_count
    })


# Data Retention Management

@router.get("/data-retention/preview")
async def preview_data_purge(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db()),
    retention_days: int = 30
):
    """Preview what data would be purged based on retention policy."""
    candidates = await get_purge_candidates(session, retention_days)
    return {
        "retention_days": retention_days,
        "preview": True,
        "summary": {
            "total_log_entries_purgeable": candidates["total_purgeable_log_entries"],
            "total_environment_logs_purgeable": candidates["total_purgeable_environment_logs"],
            "devices_analyzed": candidates["devices_analyzed"],
            "cutoff_date": candidates["cutoff_date"]
        },
        "log_entries": candidates["log_entries"],
        "environment_logs": candidates["environment_logs"]
    }


@router.post("/data-retention/purge")
async def execute_data_purge(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db()),
    retention_days: int = 30,
    confirm: bool = False
):
    """Execute data purge based on retention policy."""
    if not confirm:
        return {
            "error": "Must set confirm=true to execute purge",
            "message": "Use /admin/data-retention/preview to see what would be deleted first"
        }

    results = await purge_old_data(session, retention_days, dry_run=False)

    print(f"[DATA PURGE] Admin {admin.email} executed purge: "
          f"{results['log_entries_deleted']} log entries, "
          f"{results['environment_logs_deleted']} environment logs deleted")

    return {
        "status": "success",
        "retention_days": retention_days,
        "deleted": {
            "log_entries": results["log_entries_deleted"],
            "environment_logs": results["environment_logs_deleted"]
        },
        "details": results["details"]
    }


@router.get("/data-retention/stats")
async def get_data_retention_stats(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Get overall data retention statistics."""
    # Total plant daily logs
    total_logs_result = await session.execute(
        select(func.count(PlantDailyLog.id))
    )
    total_logs = total_logs_result.scalar()

    # Count by hydro vs environment
    hydro_logs_result = await session.execute(
        select(func.count(PlantDailyLog.id)).where(PlantDailyLog.hydro_device_id.isnot(None))
    )
    hydro_logs = hydro_logs_result.scalar()

    env_logs_result = await session.execute(
        select(func.count(PlantDailyLog.id)).where(PlantDailyLog.env_device_id.isnot(None))
    )
    env_logs = env_logs_result.scalar()

    # Legacy counts (always 0 now)
    logs_by_device = {}

    # Plants with reports vs without
    plants_with_reports_result = await session.execute(
        select(func.count(Plant.id))
        .where(Plant.end_date.isnot(None))
    )
    finished_plants = plants_with_reports_result.scalar()

    reports_count_result = await session.execute(
        select(func.count(PlantReport.id))
    )
    reports_count = reports_count_result.scalar()

    # Active plants
    active_plants_result = await session.execute(
        select(func.count(Plant.id))
        .where(Plant.end_date.is_(None))
    )
    active_plants = active_plants_result.scalar()

    return {
        "total_plant_daily_logs": total_logs,
        "plant_daily_logs_with_hydro_data": hydro_logs,
        "plant_daily_logs_with_env_data": env_logs,
        "total_log_entries": 0,  # Legacy, removed
        "total_environment_logs": 0,  # Legacy, removed
        "logs_by_device_type": logs_by_device,
        "plants": {
            "active": active_plants,
            "finished": finished_plants,
            "with_frozen_reports": reports_count
        }
    }


# Legacy Log Management (orphaned logs without device_id)

@router.get("/legacy-logs/summary")
async def get_legacy_logs_summary(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Get summary of legacy log entries. Tables removed - returns empty."""
    return {
        "total_legacy_logs": 0,
        "plants_affected": 0,
        "new_log_count": 0,
        "total_log_count": 0,
        "by_plant": [],
        "legacy_date_range": {
            "oldest": None,
            "newest": None
        },
        "note": "Legacy log tables (LogEntry, EnvironmentLog) have been removed. Using plant-centric logging (PlantDailyLog) instead."
    }


@router.get("/legacy-logs/by-plant/{plant_id}")
async def get_legacy_logs_for_plant(
    plant_id: str,
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db()),
    limit: int = 100
):
    """Get legacy log entries for a specific plant. Tables removed - returns empty."""
    # Verify plant exists
    plant_result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id)
    )
    plant = plant_result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found")

    return {
        "plant_id": plant_id,
        "plant_name": plant.name,
        "logs": [],
        "count": 0,
        "note": "Legacy log tables have been removed."
    }


@router.post("/legacy-logs/associate")
async def associate_legacy_logs_to_device(
    plant_id: str,
    device_id: str,
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Associate legacy log entries to a device. Tables removed - no-op."""
    return {
        "status": "success",
        "message": "Legacy log tables have been removed. No logs to associate.",
        "plant_id": plant_id,
        "device_id": device_id,
        "updated_count": 0
    }


@router.delete("/legacy-logs/purge")
async def purge_legacy_logs(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db()),
    plant_id: Optional[str] = None,
    confirm: bool = False
):
    """Purge legacy log entries. Tables removed - no-op."""
    return {
        "status": "success",
        "message": "Legacy log tables have been removed. No logs to purge.",
        "deleted_count": 0
    }
