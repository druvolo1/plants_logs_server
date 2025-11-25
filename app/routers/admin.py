# app/routers/admin.py
"""
Admin endpoints for user management, overview, and system monitoring.
"""
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi_users import exceptions

from app.models import User, Device, Plant, DeviceAssignment, LogEntry, EnvironmentLog
from app.schemas import UserCreate, UserUpdate, PasswordReset
from app.services.data_retention import get_purge_candidates, purge_old_data
from typing import Optional
from datetime import datetime, timedelta

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


# HTML Pages

@router.get("/overview", response_class=HTMLResponse)
async def admin_overview_page(
    request: Request,
    admin: User = Depends(get_current_admin_dependency())
):
    """Admin overview page"""
    return get_templates().TemplateResponse("admin_overview.html", {"request": request, "user": admin})


@router.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Users management page"""
    result = await session.execute(
        select(User).options(selectinload(User.oauth_accounts))
    )
    users = result.scalars().all()
    return get_templates().TemplateResponse("users.html", {"request": request, "user": admin, "users": users})


# API Endpoints

@router.get("/all-devices")
async def get_all_devices(
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get all devices in the system"""
    result = await session.execute(
        select(Device, User.email)
        .join(User, Device.user_id == User.id)
        .order_by(Device.id.desc())
    )

    devices_list = []
    for device, owner_email in result.all():
        # Check for active plant assignment
        assignment_result = await session.execute(
            select(DeviceAssignment, Plant)
            .join(Plant, DeviceAssignment.plant_id == Plant.id)
            .where(
                DeviceAssignment.device_id == device.id,
                DeviceAssignment.removed_at == None
            )
        )
        assignment_row = assignment_result.first()

        active_plant_name = None
        active_phase = None

        if assignment_row:
            assignment, plant = assignment_row
            active_plant_name = plant.name
            active_phase = plant.current_phase

        devices_list.append({
            "device_id": device.device_id,
            "name": device.name,
            "owner_email": owner_email,
            "device_type": device.device_type,
            "is_online": device.is_online,
            "active_plant_name": active_plant_name,
            "active_phase": active_phase
        })

    return devices_list


@router.get("/all-plants")
async def get_all_plants(
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get all plants in the system"""
    result = await session.execute(
        select(Plant, User.email, Device.device_id)
        .join(User, Plant.user_id == User.id)
        .outerjoin(Device, Plant.device_id == Device.id)
        .order_by(Plant.id.desc())
    )

    plants_list = []
    for plant, owner_email, device_uuid in result.all():
        plants_list.append({
            "plant_id": plant.plant_id,
            "name": plant.name,
            "owner_email": owner_email,
            "device_id": device_uuid,
            "status": plant.status,
            "current_phase": plant.current_phase,
            "start_date": plant.start_date.isoformat() if plant.start_date else None,
            "end_date": plant.end_date.isoformat() if plant.end_date else None,
            "is_active": plant.end_date is None
        })

    return plants_list


@router.get("/user-count")
async def get_user_count(
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get total user count"""
    result = await session.execute(select(func.count(User.id)))
    count = result.scalar()
    return {"count": count}


# User Management

@router.post("/users")
async def add_user(
    user_data: UserCreate,
    admin: User = Depends(get_current_admin_dependency()),
    manager = Depends(get_user_manager_dependency())
):
    """Create a new user"""
    try:
        user = await manager.create(user_data)
        return {"status": "success", "user_id": user.id}
    except exceptions.UserAlreadyExists:
        raise HTTPException(400, "User already exists")


@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    admin: User = Depends(get_current_admin_dependency()),
    manager = Depends(get_user_manager_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Update user information"""
    user = await manager.user_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_dict = {}
    if user_data.email is not None:
        update_dict["email"] = user_data.email
    if user_data.first_name is not None:
        update_dict["first_name"] = user_data.first_name
    if user_data.last_name is not None:
        update_dict["last_name"] = user_data.last_name
    if user_data.is_active is not None:
        update_dict["is_active"] = user_data.is_active
    if user_data.is_superuser is not None:
        update_dict["is_superuser"] = user_data.is_superuser

    user = await manager.user_db.update(user, update_dict)
    return {"status": "success"}


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    password_reset: PasswordReset,
    admin: User = Depends(get_current_admin_dependency()),
    manager = Depends(get_user_manager_dependency())
):
    """Reset a user's password"""
    user = await manager.user_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    hashed_password = manager.password_helper.hash(password_reset.password)
    update_dict = {"hashed_password": hashed_password}
    user = await manager.user_db.update(user, update_dict)
    return {"status": "success"}


@router.post("/users/{user_id}/suspend")
async def suspend_user(
    user_id: int,
    admin: User = Depends(get_current_admin_dependency()),
    manager = Depends(get_user_manager_dependency())
):
    """Suspend a user"""
    user = await manager.user_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    update_dict = {"is_suspended": True}
    user = await manager.user_db.update(user, update_dict)
    return {"status": "success"}


@router.post("/users/{user_id}/unsuspend")
async def unsuspend_user(
    user_id: int,
    admin: User = Depends(get_current_admin_dependency()),
    manager = Depends(get_user_manager_dependency())
):
    """Unsuspend a user"""
    user = await manager.user_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    update_dict = {"is_suspended": False}
    user = await manager.user_db.update(user, update_dict)
    return {"status": "success"}


@router.post("/users/{user_id}/approve")
async def approve_user(
    user_id: int,
    admin: User = Depends(get_current_admin_dependency()),
    manager = Depends(get_user_manager_dependency())
):
    """Approve a pending user"""
    user = await manager.user_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    update_dict = {"is_active": True}
    user = await manager.user_db.update(user, update_dict)
    return {"status": "success"}


@router.delete("/users/{user_id}")
async def delete_user_admin(
    user_id: int,
    session: AsyncSession = Depends(get_db_dependency()),
    admin: User = Depends(get_current_admin_dependency())
):
    """Delete a user"""
    user = await session.get(User, user_id)
    if user:
        await session.delete(user)
        await session.commit()
        return {"status": "success"}
    raise HTTPException(404, "User not found")


# Plant Management

@router.delete("/plants/{plant_id}", response_model=Dict[str, str])
async def delete_plant_admin(
    plant_id: str,
    user: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Delete a plant (admin only)"""
    # Get plant
    result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id)
    )

    plant = result.scalars().first()
    if not plant:
        raise HTTPException(404, "Plant not found")

    # Delete plant (logs will be cascade deleted)
    await session.delete(plant)
    await session.commit()

    return {"status": "success", "message": f"Plant '{plant.name}' and all associated logs deleted successfully"}


# Device Data View (for troubleshooting)

@router.get("/devices/{device_id}/data")
async def get_device_data(
    device_id: str,
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency()),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 1000
):
    """
    Get all log data for a specific device.
    Used for troubleshooting and data verification.
    """
    from dateutil import parser as date_parser

    # Get device
    result = await session.execute(
        select(Device, User.email)
        .join(User, Device.user_id == User.id)
        .where(Device.device_id == device_id)
    )
    row = result.first()

    if not row:
        raise HTTPException(404, "Device not found")

    device, owner_email = row

    # Parse date filters
    start_dt = None
    end_dt = None

    if start_date:
        try:
            start_dt = date_parser.isoparse(start_date)
        except Exception:
            raise HTTPException(400, "Invalid start_date format")

    if end_date:
        try:
            end_dt = date_parser.isoparse(end_date)
        except Exception:
            raise HTTPException(400, "Invalid end_date format")

    # Default to last 7 days if no date range specified
    if not start_dt and not end_dt:
        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(days=7)

    # Get log entries for this device
    log_query = select(LogEntry).where(LogEntry.device_id == device.id)

    if start_dt:
        log_query = log_query.where(LogEntry.timestamp >= start_dt)
    if end_dt:
        log_query = log_query.where(LogEntry.timestamp <= end_dt)

    log_query = log_query.order_by(LogEntry.timestamp.desc()).limit(limit)
    log_result = await session.execute(log_query)

    log_entries = []
    for log in log_result.scalars().all():
        log_entries.append({
            "id": log.id,
            "event_type": log.event_type,
            "sensor_name": log.sensor_name,
            "value": log.value,
            "dose_type": log.dose_type,
            "dose_amount_ml": log.dose_amount_ml,
            "timestamp": log.timestamp.isoformat(),
            "created_at": log.created_at.isoformat() if log.created_at else None
        })

    # Get environment logs for this device (if environmental sensor)
    env_entries = []
    if device.device_type == 'environmental':
        env_query = select(EnvironmentLog).where(EnvironmentLog.device_id == device.id)

        if start_dt:
            env_query = env_query.where(EnvironmentLog.timestamp >= start_dt)
        if end_dt:
            env_query = env_query.where(EnvironmentLog.timestamp <= end_dt)

        env_query = env_query.order_by(EnvironmentLog.timestamp.desc()).limit(limit)
        env_result = await session.execute(env_query)

        for env in env_result.scalars().all():
            env_entries.append({
                "id": env.id,
                "co2": env.co2,
                "temperature": env.temperature,
                "humidity": env.humidity,
                "vpd": env.vpd,
                "pressure": env.pressure,
                "altitude": env.altitude,
                "lux": env.lux,
                "ppfd": env.ppfd,
                "timestamp": env.timestamp.isoformat(),
                "created_at": env.created_at.isoformat() if env.created_at else None
            })

    # Get device assignment history
    assignment_result = await session.execute(
        select(DeviceAssignment, Plant)
        .join(Plant, DeviceAssignment.plant_id == Plant.id)
        .where(DeviceAssignment.device_id == device.id)
        .order_by(DeviceAssignment.assigned_at.desc())
    )

    assignments = []
    for assignment, plant in assignment_result.all():
        assignments.append({
            "plant_id": plant.plant_id,
            "plant_name": plant.name,
            "assigned_at": assignment.assigned_at.isoformat(),
            "removed_at": assignment.removed_at.isoformat() if assignment.removed_at else None,
            "is_active": assignment.removed_at is None
        })

    return {
        "device": {
            "device_id": device.device_id,
            "name": device.name,
            "device_type": device.device_type,
            "owner_email": owner_email,
            "is_online": device.is_online,
            "last_seen": device.last_seen.isoformat() if device.last_seen else None
        },
        "date_range": {
            "start": start_dt.isoformat() if start_dt else None,
            "end": end_dt.isoformat() if end_dt else None
        },
        "log_entries": log_entries,
        "environment_logs": env_entries,
        "plant_assignments": assignments,
        "counts": {
            "log_entries": len(log_entries),
            "environment_logs": len(env_entries),
            "plant_assignments": len(assignments)
        }
    }


@router.get("/devices/{device_id}/data/summary")
async def get_device_data_summary(
    device_id: str,
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Get a summary of all data stored for a device.
    Useful for understanding data volume and date ranges.
    """
    # Get device
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    # Count log entries
    log_count_result = await session.execute(
        select(func.count(LogEntry.id)).where(LogEntry.device_id == device.id)
    )
    log_count = log_count_result.scalar()

    # Get log entry date range
    log_range_result = await session.execute(
        select(func.min(LogEntry.timestamp), func.max(LogEntry.timestamp))
        .where(LogEntry.device_id == device.id)
    )
    log_range = log_range_result.first()
    log_min_date = log_range[0].isoformat() if log_range[0] else None
    log_max_date = log_range[1].isoformat() if log_range[1] else None

    # Count environment logs
    env_count_result = await session.execute(
        select(func.count(EnvironmentLog.id)).where(EnvironmentLog.device_id == device.id)
    )
    env_count = env_count_result.scalar()

    # Get environment log date range
    env_range_result = await session.execute(
        select(func.min(EnvironmentLog.timestamp), func.max(EnvironmentLog.timestamp))
        .where(EnvironmentLog.device_id == device.id)
    )
    env_range = env_range_result.first()
    env_min_date = env_range[0].isoformat() if env_range[0] else None
    env_max_date = env_range[1].isoformat() if env_range[1] else None

    # Count by event type for log entries
    event_type_result = await session.execute(
        select(LogEntry.event_type, func.count(LogEntry.id))
        .where(LogEntry.device_id == device.id)
        .group_by(LogEntry.event_type)
    )
    event_type_counts = {row[0]: row[1] for row in event_type_result.all()}

    # Count by sensor name for sensor events
    sensor_result = await session.execute(
        select(LogEntry.sensor_name, func.count(LogEntry.id))
        .where(LogEntry.device_id == device.id, LogEntry.event_type == 'sensor')
        .group_by(LogEntry.sensor_name)
    )
    sensor_counts = {row[0] or 'unknown': row[1] for row in sensor_result.all()}

    return {
        "device_id": device_id,
        "device_name": device.name,
        "device_type": device.device_type,
        "log_entries": {
            "total_count": log_count,
            "oldest": log_min_date,
            "newest": log_max_date,
            "by_event_type": event_type_counts,
            "by_sensor": sensor_counts
        },
        "environment_logs": {
            "total_count": env_count,
            "oldest": env_min_date,
            "newest": env_max_date
        }
    }


# Data Retention Management

@router.get("/data-retention/preview")
async def preview_data_purge(
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency()),
    retention_days: int = 30
):
    """
    Preview what data would be purged based on retention policy.

    Returns a list of data that can be safely deleted:
    - Data from finished plants with frozen reports past the retention buffer
    - Orphaned data from devices with no plant assignments
    """
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
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency()),
    retention_days: int = 30,
    confirm: bool = False
):
    """
    Execute data purge based on retention policy.

    CAUTION: This permanently deletes data. Use preview endpoint first.

    Args:
        retention_days: Number of days to keep data after plant is finished (default 30)
        confirm: Must be True to actually delete data
    """
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
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Get overall data retention statistics.
    """
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

    from app.models import PlantReport
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
