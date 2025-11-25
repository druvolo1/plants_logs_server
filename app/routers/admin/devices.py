# app/routers/admin/devices.py
"""
Device management and data viewing endpoints for admin portal.
"""
import json
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import User, Device, Plant, DeviceAssignment, LogEntry, EnvironmentLog
from app.routers.admin import get_current_admin_dependency, get_db_dependency, get_templates

router = APIRouter()


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
            "active_phase": active_phase,
            "last_seen": device.last_seen.isoformat() if device.last_seen else None
        })

    return devices_list


@router.get("/devices/{device_id}/data")
async def get_device_data(
    device_id: str,
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency()),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 1000
):
    """Get all log data for a specific device."""
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
    """Get a summary of all data stored for a device."""
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

    # Also count legacy logs (logs with no device_id) for troubleshooting
    legacy_count_result = await session.execute(
        select(func.count(LogEntry.id)).where(LogEntry.device_id.is_(None))
    )
    legacy_count = legacy_count_result.scalar() or 0

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
        },
        "legacy_logs_total": legacy_count
    }


# Device Heartbeat Settings (Admin Only)

@router.get("/devices/{device_id}/heartbeat-settings")
async def get_device_heartbeat_settings(
    device_id: str,
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get heartbeat settings for a device (admin only)."""
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    # Load device settings
    settings = {}
    if device.settings:
        try:
            settings = json.loads(device.settings)
        except:
            settings = {}

    return {
        "device_id": device_id,
        "device_name": device.name,
        "device_type": device.device_type,
        "use_fahrenheit": settings.get("use_fahrenheit", False),
        "update_interval": settings.get("update_interval", 30),
        "log_interval": settings.get("log_interval", 3600)
    }


@router.put("/devices/{device_id}/heartbeat-settings")
async def update_device_heartbeat_settings(
    device_id: str,
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency()),
    use_fahrenheit: Optional[bool] = None,
    update_interval: Optional[int] = None,
    log_interval: Optional[int] = None
):
    """Update heartbeat settings for a device (admin only)."""
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    # Load existing settings
    settings = {}
    if device.settings:
        try:
            settings = json.loads(device.settings)
        except:
            settings = {}

    # Track what changed for logging
    changes = []

    # Update only provided fields
    if use_fahrenheit is not None:
        old_val = settings.get("use_fahrenheit", False)
        settings["use_fahrenheit"] = use_fahrenheit
        if old_val != use_fahrenheit:
            changes.append(f"use_fahrenheit: {old_val} -> {use_fahrenheit}")

    if update_interval is not None:
        if update_interval < 5:
            raise HTTPException(400, "update_interval must be at least 5 seconds")
        if update_interval > 3600:
            raise HTTPException(400, "update_interval must be at most 3600 seconds (1 hour)")
        old_val = settings.get("update_interval", 30)
        settings["update_interval"] = update_interval
        if old_val != update_interval:
            changes.append(f"update_interval: {old_val}s -> {update_interval}s")

    if log_interval is not None:
        if log_interval < 60:
            raise HTTPException(400, "log_interval must be at least 60 seconds (1 minute)")
        if log_interval > 86400:
            raise HTTPException(400, "log_interval must be at most 86400 seconds (24 hours)")
        old_val = settings.get("log_interval", 3600)
        settings["log_interval"] = log_interval
        if old_val != log_interval:
            changes.append(f"log_interval: {old_val}s -> {log_interval}s")

    # Save updated settings
    device.settings = json.dumps(settings)
    await session.commit()

    if changes:
        print(f"[ADMIN] {admin.email} updated heartbeat settings for device {device_id}: {', '.join(changes)}")

    return {
        "status": "success",
        "device_id": device_id,
        "message": f"Settings updated. Changes will apply on next device heartbeat.",
        "settings": {
            "use_fahrenheit": settings.get("use_fahrenheit", False),
            "update_interval": settings.get("update_interval", 30),
            "log_interval": settings.get("log_interval", 3600)
        }
    }
