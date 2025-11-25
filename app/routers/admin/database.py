# app/routers/admin/database.py
"""
Database management, data retention, and legacy log management endpoints.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete

from app.models import User, Device, Plant, LogEntry, EnvironmentLog, PlantReport
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
    # Total log entries
    total_logs_result = await session.execute(
        select(func.count(LogEntry.id))
    )
    total_logs = total_logs_result.scalar()

    # Total environment logs
    total_env_result = await session.execute(
        select(func.count(EnvironmentLog.id))
    )
    total_env = total_env_result.scalar()

    # Logs by device type
    logs_by_device_result = await session.execute(
        select(Device.device_type, func.count(LogEntry.id))
        .join(Device, LogEntry.device_id == Device.id)
        .group_by(Device.device_type)
    )
    logs_by_device = {row[0] or 'unknown': row[1] for row in logs_by_device_result.all()}

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
        "total_log_entries": total_logs,
        "total_environment_logs": total_env,
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
    """Get summary of legacy log entries that have plant_id but no device_id."""
    # Count logs with plant_id but no device_id (legacy logs)
    legacy_count_result = await session.execute(
        select(func.count(LogEntry.id)).where(
            LogEntry.device_id.is_(None)
        )
    )
    legacy_count = legacy_count_result.scalar() or 0

    # Count logs with device_id (new format)
    new_count_result = await session.execute(
        select(func.count(LogEntry.id)).where(
            LogEntry.device_id.isnot(None)
        )
    )
    new_count = new_count_result.scalar() or 0

    # Get breakdown by plant for legacy logs
    by_plant = []
    try:
        plant_breakdown_result = await session.execute(
            select(
                Plant.plant_id,
                Plant.name,
                func.count(LogEntry.id).label('log_count'),
                func.min(LogEntry.timestamp).label('oldest_log'),
                func.max(LogEntry.timestamp).label('newest_log')
            )
            .select_from(LogEntry)
            .join(Plant, LogEntry.plant_id == Plant.id)
            .where(LogEntry.device_id.is_(None))
            .group_by(Plant.id, Plant.plant_id, Plant.name)
            .order_by(func.count(LogEntry.id).desc())
        )
        for row in plant_breakdown_result.all():
            by_plant.append({
                "plant_id": row[0],
                "plant_name": row[1],
                "log_count": row[2],
                "oldest_log": row[3].isoformat() if row[3] else None,
                "newest_log": row[4].isoformat() if row[4] else None
            })
    except Exception as e:
        print(f"Note: Could not get plant breakdown: {e}")

    # Get date range of legacy logs
    date_range_result = await session.execute(
        select(func.min(LogEntry.timestamp), func.max(LogEntry.timestamp))
        .where(LogEntry.device_id.is_(None))
    )
    date_range = date_range_result.first()

    return {
        "total_legacy_logs": legacy_count,
        "plants_affected": len(by_plant),
        "new_log_count": new_count,
        "total_log_count": legacy_count + new_count,
        "by_plant": by_plant,
        "legacy_date_range": {
            "oldest": date_range[0].isoformat() if date_range[0] else None,
            "newest": date_range[1].isoformat() if date_range[1] else None
        }
    }


@router.get("/legacy-logs/by-plant/{plant_id}")
async def get_legacy_logs_for_plant(
    plant_id: str,
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db()),
    limit: int = 100
):
    """Get legacy log entries for a specific plant."""
    # Get plant
    plant_result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id)
    )
    plant = plant_result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found")

    # Get legacy logs for this plant
    logs_result = await session.execute(
        select(LogEntry)
        .where(
            LogEntry.plant_id == plant.id,
            LogEntry.device_id.is_(None)
        )
        .order_by(LogEntry.timestamp.desc())
        .limit(limit)
    )

    logs = []
    for log in logs_result.scalars().all():
        logs.append({
            "id": log.id,
            "event_type": log.event_type,
            "sensor_name": log.sensor_name,
            "value": log.value,
            "dose_type": log.dose_type,
            "dose_amount_ml": log.dose_amount_ml,
            "timestamp": log.timestamp.isoformat()
        })

    return {
        "plant_id": plant_id,
        "plant_name": plant.name,
        "logs": logs,
        "count": len(logs)
    }


@router.post("/legacy-logs/associate")
async def associate_legacy_logs_to_device(
    plant_id: str,
    device_id: str,
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Associate legacy log entries to a device."""
    # Get plant
    plant_result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id)
    )
    plant = plant_result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found")

    # Get device
    device_result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = device_result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    # Update all legacy logs for this plant to use the device_id
    update_result = await session.execute(
        update(LogEntry)
        .where(
            LogEntry.plant_id == plant.id,
            LogEntry.device_id.is_(None)
        )
        .values(device_id=device.id)
    )

    await session.commit()

    updated_count = update_result.rowcount

    print(f"[LEGACY MIGRATION] Admin {admin.email} associated {updated_count} logs "
          f"from plant '{plant.name}' to device '{device.name or device.device_id}'")

    return {
        "status": "success",
        "message": f"Associated {updated_count} log entries to device",
        "plant_id": plant_id,
        "device_id": device_id,
        "updated_count": updated_count
    }


@router.delete("/legacy-logs/purge")
async def purge_legacy_logs(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db()),
    plant_id: Optional[str] = None,
    confirm: bool = False
):
    """Purge legacy log entries (with no device_id)."""
    if not confirm:
        return {
            "error": "Must set confirm=true to execute purge",
            "message": "Use /admin/legacy-logs/summary to see what would be deleted first"
        }

    if plant_id:
        # Get plant
        plant_result = await session.execute(
            select(Plant).where(Plant.plant_id == plant_id)
        )
        plant = plant_result.scalars().first()

        if not plant:
            raise HTTPException(404, "Plant not found")

        # Delete legacy logs for this plant only
        delete_result = await session.execute(
            delete(LogEntry).where(
                LogEntry.plant_id == plant.id,
                LogEntry.device_id.is_(None)
            )
        )
        deleted_count = delete_result.rowcount
        message = f"Purged {deleted_count} legacy logs for plant '{plant.name}'"
    else:
        # Delete ALL legacy logs
        delete_result = await session.execute(
            delete(LogEntry).where(LogEntry.device_id.is_(None))
        )
        deleted_count = delete_result.rowcount
        message = f"Purged {deleted_count} legacy logs (all plants)"

    await session.commit()

    print(f"[LEGACY PURGE] Admin {admin.email}: {message}")

    return {
        "status": "success",
        "message": message,
        "deleted_count": deleted_count
    }
