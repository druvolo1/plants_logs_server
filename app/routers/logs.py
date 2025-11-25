# app/routers/logs.py
"""
Log management endpoints for plant logs and environment sensor data.
"""
from typing import List, Dict, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, or_
from dateutil import parser as date_parser
import json

from app.models import User, Device, Plant, LogEntry, EnvironmentLog, DeviceAssignment, DeviceShare
from app.schemas import (
    LogEntryCreate,
    LogEntryRead,
    EnvironmentDataCreate,
    DeviceSettingsUpdate,
    DeviceSettingsResponse,
)

router = APIRouter(tags=["logs"])


def get_db_dependency():
    """Lazy import to avoid circular imports"""
    from app.main import get_db
    return get_db


def get_current_user_dependency():
    """Lazy import to avoid circular imports"""
    from app.main import current_user
    return current_user


# Plant Log Endpoints

from fastapi import Request

@router.post("/api/devices/{device_id}/logs", response_model=Dict[str, str])
async def upload_logs(
    device_id: str,
    logs: List[LogEntryCreate],
    api_key: str = Query(...),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Upload log entries from a device.

    Logs are now device-centric - stored once per device reading.
    Plant associations are determined via DeviceAssignment history when generating reports.
    """
    print(f"[LOG UPLOAD] Received {len(logs)} log entries from device {device_id}")

    # Verify device and API key
    result = await session.execute(
        select(Device).where(Device.device_id == device_id, Device.api_key == api_key)
    )
    device = result.scalars().first()

    if not device:
        raise HTTPException(401, "Invalid device or API key")

    # Insert log entries for the device (skip duplicates)
    log_count = 0
    skipped_count = 0

    for log_data in logs:
        try:
            # Parse timestamp
            timestamp = date_parser.isoparse(log_data.timestamp)

            # Check if this log entry already exists (duplicate detection by device + timestamp + event_type)
            duplicate_check = await session.execute(
                select(LogEntry).where(
                    LogEntry.device_id == device.id,
                    LogEntry.timestamp == timestamp,
                    LogEntry.event_type == log_data.event_type,
                    LogEntry.sensor_name == log_data.sensor_name if log_data.sensor_name else LogEntry.sensor_name.is_(None)
                )
            )
            existing_entry = duplicate_check.scalars().first()

            if existing_entry:
                skipped_count += 1
                continue

            # Create log entry for the device
            log_entry = LogEntry(
                device_id=device.id,
                event_type=log_data.event_type,
                sensor_name=log_data.sensor_name,
                value=log_data.value,
                dose_type=log_data.dose_type,
                dose_amount_ml=log_data.dose_amount_ml,
                timestamp=timestamp
            )

            session.add(log_entry)
            log_count += 1

        except Exception as e:
            print(f"Error inserting log entry: {e}")

    await session.commit()

    message = f"Uploaded {log_count} log entries"
    if skipped_count > 0:
        message += f", skipped {skipped_count} duplicates"
    return {"status": "success", "message": message}


@router.get("/user/plants/{plant_id}/logs", response_model=List[LogEntryRead])
async def get_plant_logs(
    plant_id: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency()),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 1000
):
    """
    Get logs for a specific plant.

    Logs are now device-centric - this endpoint queries logs from all devices
    that were assigned to the plant during the relevant time periods using
    DeviceAssignment history.
    """
    # Verify plant exists and user has access
    result = await session.execute(
        select(Plant, Device)
        .outerjoin(Device, Plant.device_id == Device.id)
        .where(
            Plant.plant_id == plant_id,
            or_(Plant.user_id == user.id, Device.user_id == user.id)
        )
    )

    row = result.first()
    if not row:
        raise HTTPException(404, "Plant not found")

    plant, device = row

    # Get all device assignments for this plant (including historical)
    assignments_result = await session.execute(
        select(DeviceAssignment).where(DeviceAssignment.plant_id == plant.id)
    )
    assignments = assignments_result.scalars().all()

    if not assignments:
        return []

    # Parse date filters
    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = date_parser.isoparse(start_date)
        except Exception as e:
            raise HTTPException(400, f"Invalid start_date format: {str(e)}")

    if end_date:
        try:
            end_dt = date_parser.isoparse(end_date)
        except Exception as e:
            raise HTTPException(400, f"Invalid end_date format: {str(e)}")

    # Build a query that gets logs from all assigned devices within their assignment periods
    # For each assignment, we need logs where:
    # - device_id matches
    # - timestamp >= assignment.assigned_at
    # - timestamp <= assignment.removed_at (or now if still active)
    all_logs = []

    for assignment in assignments:
        # Determine the time window for this assignment
        assign_start = assignment.assigned_at
        assign_end = assignment.removed_at or datetime.utcnow()

        # Apply user's date filters within the assignment window
        query_start = assign_start
        query_end = assign_end

        if start_dt and start_dt > query_start:
            query_start = start_dt
        if end_dt and end_dt < query_end:
            query_end = end_dt

        # Skip if window is invalid
        if query_start > query_end:
            continue

        # Query logs for this device during this time window
        query = select(LogEntry).where(
            LogEntry.device_id == assignment.device_id,
            LogEntry.timestamp >= query_start,
            LogEntry.timestamp <= query_end
        )

        if event_type:
            query = query.where(LogEntry.event_type == event_type)

        try:
            result = await session.execute(query)
            logs = result.scalars().all()
            all_logs.extend(logs)
        except Exception as e:
            print(f"Error querying logs for assignment {assignment.id}: {e}")

    # Sort by timestamp descending and apply limit
    all_logs.sort(key=lambda x: x.timestamp, reverse=True)
    all_logs = all_logs[:limit]

    return all_logs


# Environment Sensor Endpoints

@router.post("/api/devices/{device_id}/environment", response_model=DeviceSettingsResponse)
async def environment_heartbeat(
    device_id: str,
    data: EnvironmentDataCreate,
    api_key: str = Query(...),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Environment sensor heartbeat - updates device status and returns settings.

    This endpoint is called frequently (default: every 30 seconds) to:
    - Update device online status and last_seen timestamp
    - Receive current sensor data for real-time display (not logged to DB)
    - Return device settings (including log_interval for when to actually log)

    Note: This does NOT log data to the database. Use /environment/log for that.
    """
    # Verify device and API key
    result = await session.execute(
        select(Device).where(Device.device_id == device_id, Device.api_key == api_key)
    )
    device = result.scalars().first()

    if not device:
        # Debug: Check if device exists with different API key
        check_result = await session.execute(
            select(Device).where(Device.device_id == device_id)
        )
        existing = check_result.scalars().first()
        if existing:
            print(f"[Heartbeat] Device {device_id} exists but API key mismatch!")
            print(f"[Heartbeat] Expected key length: {len(existing.api_key)}, Received key length: {len(api_key)}")
            print(f"[Heartbeat] Expected key prefix: {existing.api_key[:8]}..., Received prefix: {api_key[:8]}...")
        else:
            print(f"[Heartbeat] Device {device_id} not found in database at all")
        raise HTTPException(404, "Device not found - please re-pair")

    # Verify device is an environmental sensor
    if device.device_type != 'environmental':
        raise HTTPException(400, "This endpoint is only for environmental sensors")

    # Update device last_seen and is_online status
    await session.execute(
        update(Device)
        .where(Device.device_id == device_id)
        .values(is_online=True, last_seen=datetime.utcnow())
    )
    await session.commit()

    # Load device settings and return to device
    settings = {}
    if device.settings:
        try:
            settings = json.loads(device.settings)
        except:
            settings = {}

    # Return settings to device (defaults: 30s heartbeat, 3600s/1hr logging)
    return DeviceSettingsResponse(
        use_fahrenheit=settings.get("use_fahrenheit", False),
        update_interval=settings.get("update_interval", 30),
        log_interval=settings.get("log_interval", 3600)
    )


@router.post("/api/devices/{device_id}/environment/log", response_model=DeviceSettingsResponse)
async def log_environment_data(
    device_id: str,
    data: EnvironmentDataCreate,
    api_key: str = Query(...),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Log environment sensor data to the database.

    This endpoint is called less frequently (default: every 60 minutes) to
    actually persist sensor data to the database for historical tracking.
    """
    # Verify device and API key
    result = await session.execute(
        select(Device).where(Device.device_id == device_id, Device.api_key == api_key)
    )
    device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found - please re-pair")

    # Verify device is an environmental sensor
    if device.device_type != 'environmental':
        raise HTTPException(400, "This endpoint is only for environmental sensors")

    # Update device last_seen and is_online status
    await session.execute(
        update(Device)
        .where(Device.device_id == device_id)
        .values(is_online=True, last_seen=datetime.utcnow())
    )

    # Parse timestamp
    try:
        timestamp = date_parser.isoparse(data.timestamp)
    except Exception as e:
        raise HTTPException(400, f"Invalid timestamp format: {str(e)}")

    # Create environment log entry
    env_log = EnvironmentLog(
        device_id=device.id,
        location_id=device.location_id,
        co2=data.co2,
        temperature=data.temperature,
        humidity=data.humidity,
        vpd=data.vpd,
        pressure=data.pressure,
        altitude=data.altitude,
        gas_resistance=data.gas_resistance,
        air_quality_score=data.air_quality_score,
        lux=data.lux,
        ppfd=data.ppfd,
        timestamp=timestamp
    )

    session.add(env_log)
    await session.commit()

    # Load device settings and return to device
    settings = {}
    if device.settings:
        try:
            settings = json.loads(device.settings)
        except:
            settings = {}

    # Return settings to device
    return DeviceSettingsResponse(
        use_fahrenheit=settings.get("use_fahrenheit", False),
        update_interval=settings.get("update_interval", 30),
        log_interval=settings.get("log_interval", 3600)
    )


@router.patch("/api/devices/{device_id}/settings", response_model=DeviceSettingsResponse)
async def update_device_settings(
    device_id: str,
    settings_update: DeviceSettingsUpdate,
    api_key: str = Header(..., alias="X-API-Key"),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Update device settings (temperature unit, update interval, log interval, etc.)"""
    # Verify device exists and API key matches
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalars().first()

    if not device or device.api_key != api_key:
        raise HTTPException(401, "Invalid device ID or API key")

    # Load existing settings or create new dict
    if device.settings:
        try:
            settings = json.loads(device.settings)
        except:
            settings = {}
    else:
        settings = {}

    # Update only provided fields
    if settings_update.use_fahrenheit is not None:
        settings["use_fahrenheit"] = settings_update.use_fahrenheit
        print(f"[Device {device_id}] Temperature unit updated to: {'Fahrenheit' if settings_update.use_fahrenheit else 'Celsius'}")

    if settings_update.update_interval is not None:
        settings["update_interval"] = settings_update.update_interval
        print(f"[Device {device_id}] Heartbeat interval updated to: {settings_update.update_interval}s")

    if settings_update.log_interval is not None:
        settings["log_interval"] = settings_update.log_interval
        print(f"[Device {device_id}] Log interval updated to: {settings_update.log_interval}s")

    # Save updated settings
    device.settings = json.dumps(settings)
    await session.commit()

    # Return current settings
    return DeviceSettingsResponse(
        use_fahrenheit=settings.get("use_fahrenheit", False),
        update_interval=settings.get("update_interval", 30),
        log_interval=settings.get("log_interval", 3600)
    )


@router.get("/api/devices/{device_id}/environment/latest")
async def get_latest_environment_data(
    device_id: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get the latest environment sensor reading for a device"""
    # Verify device exists and user has access
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    # Check ownership or shared access
    if device.user_id != user.id:
        # Check if device is shared with this user
        share_result = await session.execute(
            select(DeviceShare).where(
                DeviceShare.device_id == device.id,
                DeviceShare.shared_with_user_id == user.id,
                DeviceShare.accepted_at.isnot(None)
            )
        )
        share = share_result.scalars().first()
        if not share:
            raise HTTPException(403, "Access denied")

    # Get latest environment log entry
    env_result = await session.execute(
        select(EnvironmentLog)
        .where(EnvironmentLog.device_id == device.id)
        .order_by(EnvironmentLog.timestamp.desc())
        .limit(1)
    )
    env_log = env_result.scalars().first()

    # Get device settings for temperature unit
    settings = {}
    if device.settings:
        try:
            settings = json.loads(device.settings)
        except:
            settings = {}
    use_fahrenheit = settings.get("use_fahrenheit", False)

    if not env_log:
        # No data yet
        return {
            "device_id": device_id,
            "has_data": False,
            "is_online": device.is_online,
            "last_seen": device.last_seen,
            "use_fahrenheit": use_fahrenheit
        }

    # Return the latest data
    return {
        "device_id": device_id,
        "has_data": True,
        "is_online": device.is_online,
        "last_seen": device.last_seen,
        "use_fahrenheit": use_fahrenheit,
        "co2": env_log.co2,
        "temperature": env_log.temperature,
        "humidity": env_log.humidity,
        "vpd": env_log.vpd,
        "pressure": env_log.pressure,
        "altitude": env_log.altitude,
        "gas_resistance": env_log.gas_resistance,
        "air_quality_score": env_log.air_quality_score,
        "lux": env_log.lux,
        "ppfd": env_log.ppfd,
        "timestamp": env_log.timestamp,
        "created_at": env_log.created_at
    }
