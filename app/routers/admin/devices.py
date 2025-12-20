# app/routers/admin/devices.py
"""
Device management and data viewing endpoints for admin portal.
"""
import json
import os
from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from app.models import User, Device, Plant, DeviceAssignment, LogEntry, EnvironmentLog, DeviceDebugLog

# Log storage directory
LOGS_DIR = Path("logs/device_debug")

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
@router.get("/devices", response_class=HTMLResponse)
async def admin_devices_page(
    request: Request,
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Admin devices management page"""
    # Count pending users for sidebar badge
    pending_result = await session.execute(
        select(func.count(User.id)).where(User.is_active == False)
    )
    pending_count = pending_result.scalar() or 0

    return _get_templates().TemplateResponse("admin_devices.html", {
        "request": request,
        "user": admin,
        "active_page": "devices",
        "pending_users_count": pending_count
    })


@router.get("/all-devices")
async def get_all_devices(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
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
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db()),
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
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
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
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
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
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db()),
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


@router.put("/devices/{device_id}/reboot")
async def queue_device_reboot(
    device_id: str,
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Queue a reboot command for a device (admin only).

    The device will reboot on its next heartbeat when it sees pending_reboot=True.
    """
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

    # Set pending_reboot flag
    settings["pending_reboot"] = True

    # Save updated settings
    device.settings = json.dumps(settings)
    await session.commit()

    print(f"[ADMIN] {admin.email} queued reboot for device {device_id}")

    return {
        "status": "success",
        "device_id": device_id,
        "message": "Reboot queued. Device will restart on next heartbeat."
    }


# =============================================================================
# Device Debug Log Management
# =============================================================================

@router.post("/devices/{device_id}/logs/request")
async def request_device_log(
    device_id: str,
    duration: int,
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Request a debug log capture from a device.

    For valve_controller devices: Sends command immediately via WebSocket.
    For environmental devices: Creates pending request, delivered via next heartbeat.
    """
    # Validate duration (1 second to 10 minutes)
    if duration < 1 or duration > 600:
        raise HTTPException(400, "Duration must be between 1 and 600 seconds")

    # Get device
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    if not device.is_online:
        raise HTTPException(400, "Device is offline. Cannot request log capture.")

    # Check if there's already a pending/capturing log for this device
    existing_result = await session.execute(
        select(DeviceDebugLog).where(
            DeviceDebugLog.device_id == device.id,
            DeviceDebugLog.status.in_(['pending', 'capturing'])
        )
    )
    existing = existing_result.scalars().first()
    if existing:
        raise HTTPException(400, "A log capture is already in progress for this device")

    # Create log request record
    filename = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S") + ".txt"
    log_record = DeviceDebugLog(
        device_id=device.id,
        filename=filename,
        requested_duration=duration,
        status='pending',
        requested_at=datetime.utcnow(),
        requested_by_user_id=admin.id
    )
    session.add(log_record)
    await session.commit()
    await session.refresh(log_record)

    # For valve_controller devices with WebSocket: send command immediately
    # For environmental devices: leave as pending, heartbeat will deliver it
    message = ""
    if device.device_type == 'valve_controller':
        from app.routers.websocket import device_connections
        if device_id in device_connections:
            try:
                await device_connections[device_id].send_json({
                    "type": "start_remote_log",
                    "log_id": log_record.id,
                    "duration": duration
                })
                print(f"[DEBUG_LOG] Sent start_remote_log command to {device_id} for {duration}s (log_id={log_record.id})")
                message = f"Log capture started for {duration} seconds"
            except Exception as e:
                print(f"[DEBUG_LOG] Failed to send command to device {device_id}: {e}")
                log_record.status = 'failed'
                log_record.early_cutoff_reason = f"WebSocket send failed: {str(e)}"
                await session.commit()
                raise HTTPException(500, f"Failed to send command to device: {str(e)}")
        else:
            log_record.status = 'failed'
            log_record.early_cutoff_reason = "Device disconnected"
            await session.commit()
            raise HTTPException(400, "Device disconnected")
    else:
        # Environmental devices receive the request via heartbeat
        message = f"Log capture requested for {duration} seconds. Will start on next device heartbeat."
        print(f"[DEBUG_LOG] Queued remote log request for {device_id}: log_id={log_record.id}, duration={duration}s (via heartbeat)")

    print(f"[ADMIN] {admin.email} requested {duration}s debug log from device {device_id}")

    return {
        "status": "success",
        "log_id": log_record.id,
        "message": message
    }


@router.get("/devices/{device_id}/logs")
async def list_device_logs(
    device_id: str,
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """List all debug logs for a device."""
    # Get device
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    # Get all logs for this device
    logs_result = await session.execute(
        select(DeviceDebugLog, User.email)
        .outerjoin(User, DeviceDebugLog.requested_by_user_id == User.id)
        .where(DeviceDebugLog.device_id == device.id)
        .order_by(DeviceDebugLog.requested_at.desc())
    )

    logs = []
    for log, requester_email in logs_result.all():
        logs.append({
            "id": log.id,
            "filename": log.filename,
            "requested_duration": log.requested_duration,
            "actual_duration": log.actual_duration,
            "file_size": log.file_size,
            "status": log.status,
            "early_cutoff_reason": log.early_cutoff_reason,
            "requested_at": log.requested_at.isoformat() if log.requested_at else None,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "completed_at": log.completed_at.isoformat() if log.completed_at else None,
            "requested_by": requester_email
        })

    return {"logs": logs}


@router.get("/devices/{device_id}/logs/{log_id}/download")
async def download_device_log(
    device_id: str,
    log_id: int,
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Download a debug log file."""
    # Get device
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    # Get log record
    log_result = await session.execute(
        select(DeviceDebugLog).where(
            DeviceDebugLog.id == log_id,
            DeviceDebugLog.device_id == device.id
        )
    )
    log = log_result.scalars().first()

    if not log:
        raise HTTPException(404, "Log not found")

    if log.status != 'completed':
        raise HTTPException(400, f"Log is not ready for download (status: {log.status})")

    # Build file path
    file_path = LOGS_DIR / device_id / log.filename

    if not file_path.exists():
        raise HTTPException(404, "Log file not found on disk")

    return FileResponse(
        path=file_path,
        filename=f"{device_id}_{log.filename}",
        media_type="text/plain"
    )


@router.delete("/devices/{device_id}/logs/{log_id}")
async def delete_device_log(
    device_id: str,
    log_id: int,
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Delete a debug log."""
    # Get device
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    # Get log record
    log_result = await session.execute(
        select(DeviceDebugLog).where(
            DeviceDebugLog.id == log_id,
            DeviceDebugLog.device_id == device.id
        )
    )
    log = log_result.scalars().first()

    if not log:
        raise HTTPException(404, "Log not found")

    # Delete file from disk if it exists
    file_path = LOGS_DIR / device_id / log.filename
    if file_path.exists():
        try:
            file_path.unlink()
            print(f"[DEBUG_LOG] Deleted file: {file_path}")
        except Exception as e:
            print(f"[DEBUG_LOG] Failed to delete file {file_path}: {e}")

    # Delete database record
    await session.delete(log)
    await session.commit()

    print(f"[ADMIN] {admin.email} deleted debug log {log_id} for device {device_id}")

    return {"status": "success", "message": "Log deleted"}


# =============================================================================
# Device Status Management
# =============================================================================

@router.put("/devices/{device_id}/set-offline")
async def set_device_offline(
    device_id: str,
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Manually mark a device as offline (admin only).

    Useful when a device crashed or disconnected ungracefully and is still
    showing as online in the database.
    """
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    was_online = device.is_online
    device.is_online = False
    device.last_seen = datetime.utcnow()
    await session.commit()

    print(f"[ADMIN] {admin.email} manually set device {device_id} offline (was_online={was_online})")

    return {
        "status": "success",
        "device_id": device_id,
        "message": f"Device marked offline (was {'online' if was_online else 'already offline'})"
    }


@router.put("/devices/reset-all-offline")
async def reset_all_devices_offline(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Mark all devices as offline (admin only).

    Useful after server restart to reset stale online status.
    Devices will be marked online again when they reconnect.
    """
    result = await session.execute(
        update(Device)
        .where(Device.is_online == True)
        .values(is_online=False, last_seen=datetime.utcnow())
    )
    await session.commit()

    count = result.rowcount

    print(f"[ADMIN] {admin.email} reset all devices to offline (affected {count} devices)")

    return {
        "status": "success",
        "message": f"Marked {count} devices as offline"
    }
