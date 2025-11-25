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
    plant_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Upload log entries from a device"""
    print(f"[LOG UPLOAD] Received {len(logs)} log entries from device {device_id}")
    # Verify device and API key
    result = await session.execute(select(Device).where(Device.device_id == device_id, Device.api_key == api_key))
    device = result.scalars().first()

    if not device:
        raise HTTPException(401, "Invalid device or API key")

    # Get target plants - either specific plant or all assigned plants
    target_plants = []

    if plant_id:
        # Legacy mode: specific plant_id provided (backward compatibility)
        # Try legacy direct assignment first
        result = await session.execute(select(Plant).where(Plant.plant_id == plant_id, Plant.device_id == device.id))
        plant = result.scalars().first()

        # If not found via legacy direct assignment, try DeviceAssignment table
        if not plant:
            result = await session.execute(
                select(Plant)
                .join(DeviceAssignment, DeviceAssignment.plant_id == Plant.id)
                .where(
                    Plant.plant_id == plant_id,
                    DeviceAssignment.device_id == device.id,
                    DeviceAssignment.removed_at == None
                )
            )
            plant = result.scalars().first()

        if not plant:
            print(f"[LOG UPLOAD ERROR] Plant not found: plant_id={plant_id}, device.id={device.id}")
            raise HTTPException(404, f"Plant {plant_id} not found for device {device_id}")

        target_plants = [plant]
    else:
        # New mode: log for ALL plants currently assigned to this device
        result = await session.execute(
            select(Plant)
            .join(DeviceAssignment, DeviceAssignment.plant_id == Plant.id)
            .where(
                DeviceAssignment.device_id == device.id,
                DeviceAssignment.removed_at == None,
                Plant.end_date == None  # Active plants have no end_date
            )
        )
        target_plants = result.scalars().all()

        if not target_plants:
            print(f"[LOG UPLOAD] No active plants assigned to device {device_id}")
            return {"status": "success", "message": "No active plants to log for"}

    # Insert log entries for each target plant (skip duplicates)
    log_count = 0
    skipped_count = 0

    for log_data in logs:
        try:
            # Parse timestamp
            timestamp = date_parser.isoparse(log_data.timestamp)

            # Create log entry for each target plant
            for plant in target_plants:
                # Check if this log entry already exists (duplicate detection)
                duplicate_check = await session.execute(
                    select(LogEntry).where(
                        LogEntry.plant_id == plant.id,
                        LogEntry.timestamp == timestamp,
                        LogEntry.event_type == log_data.event_type
                    )
                )
                existing_entry = duplicate_check.scalars().first()

                if existing_entry:
                    skipped_count += 1
                    continue

                # Create log entry
                log_entry = LogEntry(
                    plant_id=plant.id,
                    event_type=log_data.event_type,
                    sensor_name=log_data.sensor_name,
                    value=log_data.value,
                    dose_type=log_data.dose_type,
                    dose_amount_ml=log_data.dose_amount_ml,
                    timestamp=timestamp,
                    phase=plant.current_phase
                )

                session.add(log_entry)
                log_count += 1

        except Exception as e:
            print(f"Error inserting log entry: {e}")

    await session.commit()

    plants_count = len(target_plants)
    message = f"Uploaded {log_count} log entries for {plants_count} plant(s)"
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
    """Get logs for a specific plant"""
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

    # Build query
    query = select(LogEntry).where(LogEntry.plant_id == plant.id)

    # Apply filters
    if start_date:
        try:
            start_dt = date_parser.isoparse(start_date)
            query = query.where(LogEntry.timestamp >= start_dt)
        except Exception as e:
            print(f"Error parsing start_date: {e}")
            raise HTTPException(400, f"Invalid start_date format: {str(e)}")

    if end_date:
        try:
            end_dt = date_parser.isoparse(end_date)
            query = query.where(LogEntry.timestamp <= end_dt)
        except Exception as e:
            print(f"Error parsing end_date: {e}")
            raise HTTPException(400, f"Invalid end_date format: {str(e)}")

    if event_type:
        query = query.where(LogEntry.event_type == event_type)

    # Order by timestamp and limit
    query = query.order_by(LogEntry.timestamp.desc()).limit(limit)

    try:
        result = await session.execute(query)
        logs = result.scalars().all()
    except Exception as e:
        print(f"Error executing logs query: {e}")
        raise HTTPException(500, "Error retrieving logs")

    return logs


# Environment Sensor Endpoints

@router.post("/api/devices/{device_id}/environment", response_model=DeviceSettingsResponse)
async def upload_environment_data(
    device_id: str,
    data: EnvironmentDataCreate,
    api_key: str = Query(...),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Receive environment sensor data from device and return device settings"""
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
        update_interval=settings.get("update_interval", 60)
    )


@router.patch("/api/devices/{device_id}/settings", response_model=DeviceSettingsResponse)
async def update_device_settings(
    device_id: str,
    settings_update: DeviceSettingsUpdate,
    api_key: str = Header(..., alias="X-API-Key"),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Update device settings (temperature unit, update interval, etc.)"""
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
        print(f"[Device {device_id}] Update interval updated to: {settings_update.update_interval}s")

    # Save updated settings
    device.settings = json.dumps(settings)
    await session.commit()

    # Return current settings
    return DeviceSettingsResponse(
        use_fahrenheit=settings.get("use_fahrenheit", False),
        update_interval=settings.get("update_interval", 60)
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

    if not env_log:
        # No data yet
        return {
            "device_id": device_id,
            "has_data": False,
            "is_online": device.is_online,
            "last_seen": device.last_seen
        }

    # Return the latest data
    return {
        "device_id": device_id,
        "has_data": True,
        "is_online": device.is_online,
        "last_seen": device.last_seen,
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
