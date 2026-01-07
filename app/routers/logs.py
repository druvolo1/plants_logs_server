# app/routers/logs.py
"""
Plant-centric logging endpoints for hydro controllers and environment sensors.
"""
from typing import List, Dict, Optional
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, or_, and_
from dateutil import parser as date_parser
import json

from app.models import (
    User, Device, Plant, PlantDailyLog, DeviceAssignment, DeviceShare,
    Firmware, DeviceFirmwareAssignment, DeviceDebugLog, Location, DosingEvent, LightEvent,
    PhaseHistory
)
from app.schemas import (
    HydroReadingCreate,
    EnvironmentDataCreate,
    PlantDailyLogRead,
    DeviceSettingsUpdate,
    DeviceSettingsResponse,
    FirmwareInfo,
    RemoteLogRequest,
    EnvironmentDailyReport,
    HydroDailyReport,
    DosingEventSchema,
)
from app.services import (
    get_device_posting_slot,
    assign_posting_slot
)

router = APIRouter(tags=["logs"])

# In-memory cache for real-time environment sensor data (updated by heartbeat)
# Key: device_id (string), Value: dict with sensor data and timestamp
environment_cache: Dict[str, Dict] = {}


def get_db_dependency():
    """Lazy import to avoid circular imports"""
    from app.main import get_db
    return get_db


def get_current_user_dependency():
    """Lazy import to avoid circular imports"""
    from app.main import current_user
    return current_user


async def get_effective_user(
    request: Request,
    user: User,
    session: AsyncSession
) -> User:
    """
    Get the effective user for data display.
    If admin is impersonating another user, return that user.
    Otherwise return the actual logged-in user.
    """
    if user.is_superuser:
        impersonated_id = request.cookies.get("impersonate_user_id")
        if impersonated_id:
            try:
                target = await session.get(User, int(impersonated_id))
                if target:
                    return target
            except (ValueError, TypeError):
                pass
    return user


def update_aggregate(current_min, current_max, current_avg, current_count, new_value):
    """
    Update min/max/avg aggregates with a new value.
    Returns (new_min, new_max, new_avg, new_count)
    """
    if current_min is None:
        # First reading
        return new_value, new_value, new_value, 1

    new_min = min(current_min, new_value)
    new_max = max(current_max, new_value)
    new_avg = ((current_avg * current_count) + new_value) / (current_count + 1)
    return new_min, new_max, new_avg, current_count + 1


async def get_firmware_info_for_device(
    session: AsyncSession,
    device: Device,
    current_version: Optional[str]
) -> Optional[FirmwareInfo]:
    """
    Check if a firmware update is available for a device.
    Returns FirmwareInfo with update details, or None if no update available.
    """
    if not current_version:
        return None

    # Check for device-specific assignment first
    assignment_result = await session.execute(
        select(DeviceFirmwareAssignment, Firmware)
        .join(Firmware, DeviceFirmwareAssignment.firmware_id == Firmware.id)
        .where(DeviceFirmwareAssignment.device_id == device.id)
    )
    assignment_row = assignment_result.first()

    if assignment_row:
        assignment, firmware = assignment_row

        # Device has a specific assignment
        if firmware.version != current_version or assignment.force_update:
            # Capture force_update value before clearing
            should_force = assignment.force_update

            # Clear force_update flag after sending it once
            if assignment.force_update:
                assignment.force_update = False
                await session.commit()

            return FirmwareInfo(
                update_available=True,
                current_version=current_version,
                latest_version=firmware.version,
                firmware_url=f"/api/firmware/download/{firmware.device_type}/{firmware.version}",
                release_notes=firmware.release_notes,
                force_update=should_force,
                file_size=firmware.file_size,
                checksum=firmware.checksum
            )
        else:
            # Device is up to date with assigned version
            return FirmwareInfo(
                update_available=False,
                current_version=current_version,
                latest_version=firmware.version
            )

    # No specific assignment - check for latest firmware
    latest_result = await session.execute(
        select(Firmware).where(
            Firmware.device_type == device.device_type,
            Firmware.is_latest == True
        )
    )
    latest_firmware = latest_result.scalars().first()

    if not latest_firmware:
        # No firmware uploaded for this device type yet
        return FirmwareInfo(
            update_available=False,
            current_version=current_version
        )

    if latest_firmware.version != current_version:
        return FirmwareInfo(
            update_available=True,
            current_version=current_version,
            latest_version=latest_firmware.version,
            firmware_url=f"/api/firmware/download/{latest_firmware.device_type}/{latest_firmware.version}",
            release_notes=latest_firmware.release_notes,
            force_update=False,
            file_size=latest_firmware.file_size,
            checksum=latest_firmware.checksum
        )

    # Device is up to date
    return FirmwareInfo(
        update_available=False,
        current_version=current_version,
        latest_version=latest_firmware.version
    )


# Hydro Controller Endpoints

@router.post("/api/devices/{device_id}/hydro/readings", response_model=DeviceSettingsResponse)
async def log_hydro_readings(
    device_id: str,
    reading: HydroReadingCreate,
    api_key: str = Query(...),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Hydro controller posts sensor readings (4x per day).
    Writes data to all plants currently assigned to this device.
    """
    print(f"[HYDRO LOG] Received reading from device {device_id}")

    # Verify device and API key
    result = await session.execute(
        select(Device).where(Device.device_id == device_id, Device.api_key == api_key)
    )
    device = result.scalars().first()

    if not device:
        raise HTTPException(401, "Invalid device or API key")

    # Verify device is a hydro controller
    if device.device_type not in ['feeding_system', 'hydroponic_controller']:
        raise HTTPException(400, "This endpoint is only for hydro controllers")

    # Update device last_seen and is_online status
    now = datetime.utcnow()
    update_values = {
        'is_online': True,
        'last_seen': now
    }

    # Update mDNS hostname if provided
    if reading.mdns_hostname:
        if device.mdns_hostname != reading.mdns_hostname:
            print(f"[HYDRO LOG] Updated mDNS hostname for {device_id}: {reading.mdns_hostname}")
        update_values['mdns_hostname'] = reading.mdns_hostname

    # Update IP address if provided
    if reading.ip_address:
        if device.ip_address != reading.ip_address:
            print(f"[HYDRO LOG] Updated IP address for {device_id}: {reading.ip_address}")
        update_values['ip_address'] = reading.ip_address

    await session.execute(
        update(Device)
        .where(Device.device_id == device_id)
        .values(**update_values)
    )

    # Parse timestamp
    try:
        timestamp = date_parser.isoparse(reading.timestamp)
        log_date = timestamp.date()
    except Exception as e:
        raise HTTPException(400, f"Invalid timestamp format: {str(e)}")

    # Find all plants currently assigned to this device
    assignments_result = await session.execute(
        select(DeviceAssignment, Plant)
        .join(Plant, DeviceAssignment.plant_id == Plant.id)
        .where(
            DeviceAssignment.device_id == device.id,
            DeviceAssignment.removed_at.is_(None)  # Only active assignments
        )
    )
    assignments = assignments_result.all()

    if not assignments:
        print(f"[HYDRO LOG] No active plants assigned to device {device_id}")
        # Still return success - device posted data successfully
    else:
        print(f"[HYDRO LOG] Updating {len(assignments)} plant logs")

    # Update each assigned plant's daily log
    for assignment, plant in assignments:
        # Get or create today's log entry for this plant
        log_result = await session.execute(
            select(PlantDailyLog).where(
                PlantDailyLog.plant_id == plant.id,
                PlantDailyLog.log_date == log_date
            )
        )
        log = log_result.scalars().first()

        if not log:
            # Create new daily log entry
            log = PlantDailyLog(
                plant_id=plant.id,
                log_date=log_date,
                hydro_device_id=device.id,
                last_hydro_reading=timestamp,
                readings_count=0
            )
            session.add(log)
            await session.flush()  # Get the log ID

        # Update aggregates with new readings
        if reading.ph is not None:
            log.ph_min, log.ph_max, log.ph_avg, _ = update_aggregate(
                log.ph_min, log.ph_max, log.ph_avg, log.readings_count or 0, reading.ph
            )

        if reading.ec is not None:
            log.ec_min, log.ec_max, log.ec_avg, _ = update_aggregate(
                log.ec_min, log.ec_max, log.ec_avg, log.readings_count or 0, reading.ec
            )

        if reading.tds is not None:
            log.tds_min, log.tds_max, log.tds_avg, _ = update_aggregate(
                log.tds_min, log.tds_max, log.tds_avg, log.readings_count or 0, reading.tds
            )

        if reading.water_temp is not None:
            log.water_temp_min, log.water_temp_max, log.water_temp_avg, _ = update_aggregate(
                log.water_temp_min, log.water_temp_max, log.water_temp_avg, log.readings_count or 0, reading.water_temp
            )

        # Update dosing totals
        if reading.dose_ph_up_ml is not None:
            log.total_ph_up_ml = (log.total_ph_up_ml or 0) + reading.dose_ph_up_ml
            log.dosing_events_count = (log.dosing_events_count or 0) + 1

        if reading.dose_ph_down_ml is not None:
            log.total_ph_down_ml = (log.total_ph_down_ml or 0) + reading.dose_ph_down_ml
            log.dosing_events_count = (log.dosing_events_count or 0) + 1

        # Update metadata
        log.hydro_device_id = device.id
        log.last_hydro_reading = timestamp
        log.readings_count = (log.readings_count or 0) + 1
        log.updated_at = now

    await session.commit()

    # Load device settings
    settings = {}
    if device.settings:
        try:
            settings = json.loads(device.settings)
        except:
            settings = {}

    # Check for firmware updates
    firmware_info = await get_firmware_info_for_device(
        session, device, reading.firmware_version
    )

    # Check for pending reboot command
    pending_reboot = settings.get("pending_reboot", False)
    if pending_reboot:
        settings["pending_reboot"] = False
        device.settings = json.dumps(settings)
        await session.commit()
        print(f"[HYDRO LOG] Device {device_id} will reboot")

    # Get or assign posting slot for daily reporting
    posting_slot = await get_device_posting_slot(device.id, session)
    if posting_slot is None:
        try:
            posting_slot = await assign_posting_slot(device.id, session)
            print(f"[HYDRO LOG] Assigned posting slot {posting_slot} to device {device_id}")
        except ValueError as e:
            # Device type doesn't need a posting slot
            print(f"[HYDRO LOG] Could not assign posting slot: {e}")
            posting_slot = None

    # Return settings to device
    return DeviceSettingsResponse(
        use_fahrenheit=settings.get("use_fahrenheit", False),
        update_interval=settings.get("update_interval", 14400),  # 4 hours default
        log_interval=settings.get("log_interval", 14400),  # 4 hours default
        firmware=firmware_info,
        pending_reboot=pending_reboot,
        posting_slot=posting_slot
    )


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
    This endpoint is called frequently (default: every 30 seconds) for real-time display.
    Does NOT log to database - use /environment/readings for that.
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
    now = datetime.utcnow()
    update_values = {
        'is_online': True,
        'last_seen': now
    }

    # Update mDNS hostname if provided
    if data.mdns_hostname:
        if device.mdns_hostname != data.mdns_hostname:
            print(f"[ENV HEARTBEAT] Updated mDNS hostname for {device_id}: {data.mdns_hostname}")
        update_values['mdns_hostname'] = data.mdns_hostname

    # Update IP address if provided
    if data.ip_address:
        if device.ip_address != data.ip_address:
            print(f"[ENV HEARTBEAT] Updated IP address for {device_id}: {data.ip_address}")
        update_values['ip_address'] = data.ip_address

    await session.execute(
        update(Device)
        .where(Device.device_id == device_id)
        .values(**update_values)
    )
    await session.commit()

    # Load device settings
    settings = {}
    if device.settings:
        try:
            settings = json.loads(device.settings)
        except:
            settings = {}

    # Sync device-local settings to database (device is source of truth)
    settings_updated = False
    if data.use_fahrenheit is not None and settings.get("use_fahrenheit") != data.use_fahrenheit:
        settings["use_fahrenheit"] = data.use_fahrenheit
        settings_updated = True
        print(f"[ENV HEARTBEAT] Updated use_fahrenheit to {data.use_fahrenheit} for {device_id}")

    if data.light_threshold is not None and settings.get("light_threshold") != data.light_threshold:
        settings["light_threshold"] = data.light_threshold
        settings_updated = True
        print(f"[ENV HEARTBEAT] Updated light_threshold to {data.light_threshold} for {device_id}")

    if settings_updated:
        device.settings = json.dumps(settings)
        await session.commit()

    # Cache the real-time sensor data for dashboard display
    # Note: temperature is in Celsius, use_fahrenheit determines display conversion
    environment_cache[device_id] = {
        "firmware_version": data.firmware_version,
        "co2": data.co2,
        "temperature": data.temperature,  # Always Celsius
        "humidity": data.humidity,
        "vpd": data.vpd,
        "pressure": data.pressure,
        "altitude": data.altitude,
        "gas_resistance": data.gas_resistance,
        "air_quality_score": data.air_quality_score,
        "lux": data.lux,
        "ppfd": data.ppfd,
        "timestamp": data.timestamp,
        "cached_at": now.isoformat(),
        "use_fahrenheit": data.use_fahrenheit if data.use_fahrenheit is not None else settings.get("use_fahrenheit", False)
    }

    # Check for firmware updates
    firmware_info = await get_firmware_info_for_device(
        session, device, data.firmware_version
    )

    # Check for pending reboot command
    pending_reboot = settings.get("pending_reboot", False)
    if pending_reboot:
        settings["pending_reboot"] = False
        device.settings = json.dumps(settings)
        await session.commit()
        print(f"[ENV HEARTBEAT] Device {device_id} will reboot")

    # Check for pending remote log request
    remote_log_info = None
    pending_log_result = await session.execute(
        select(DeviceDebugLog).where(
            DeviceDebugLog.device_id == device.id,
            DeviceDebugLog.status == 'pending'
        ).order_by(DeviceDebugLog.requested_at.asc())
    )
    pending_log = pending_log_result.scalars().first()

    if pending_log:
        remote_log_info = RemoteLogRequest(
            log_id=pending_log.id,
            duration=pending_log.requested_duration
        )
        pending_log.status = 'capturing'
        pending_log.started_at = datetime.utcnow()
        await session.commit()
        print(f"[ENV HEARTBEAT] Sending remote log request to {device_id}")

    # Get or assign posting slot for daily reporting
    posting_slot = await get_device_posting_slot(device.id, session)
    if posting_slot is None:
        try:
            posting_slot = await assign_posting_slot(device.id, session)
            print(f"[ENV HEARTBEAT] Assigned posting slot {posting_slot} to device {device_id}")
        except ValueError as e:
            # Device type doesn't need a posting slot (shouldn't happen for environmental)
            print(f"[ENV HEARTBEAT] Could not assign posting slot: {e}")
            posting_slot = None

    # Get light threshold from settings (default 10.0 lux)
    light_threshold = settings.get("light_threshold", 10.0)

    # Return settings to device
    return DeviceSettingsResponse(
        use_fahrenheit=settings.get("use_fahrenheit", False),
        update_interval=settings.get("update_interval", 30),  # 30s heartbeat
        log_interval=0,  # Disabled - using daily reporting instead
        firmware=firmware_info,
        pending_reboot=pending_reboot,
        remote_log=remote_log_info,
        posting_slot=posting_slot,
        light_threshold=light_threshold
    )


# Plant Log Retrieval Endpoints

@router.get("/user/plants/{plant_id}/logs")
async def get_plant_logs(
    request: Request,
    plant_id: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency()),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 365
):
    """
    Get daily logs and phase history for a specific plant.
    Returns both logs data and phase timeline for chart backgrounds.
    """
    # Get effective user (handles impersonation)
    effective_user = await get_effective_user(request, user, session)

    # Verify plant exists and user has access
    result = await session.execute(
        select(Plant).where(
            Plant.plant_id == plant_id,
            Plant.user_id == effective_user.id
        )
    )
    plant = result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found")

    # Parse date filters
    query = select(PlantDailyLog).where(PlantDailyLog.plant_id == plant.id)

    if start_date:
        try:
            start_dt = date_parser.isoparse(start_date).date()
            query = query.where(PlantDailyLog.log_date >= start_dt)
        except Exception as e:
            raise HTTPException(400, f"Invalid start_date format: {str(e)}")

    if end_date:
        try:
            end_dt = date_parser.isoparse(end_date).date()
            query = query.where(PlantDailyLog.log_date <= end_dt)
        except Exception as e:
            raise HTTPException(400, f"Invalid end_date format: {str(e)}")

    # Order by date descending and limit
    query = query.order_by(PlantDailyLog.log_date.desc()).limit(limit)

    result = await session.execute(query)
    logs = result.scalars().all()

    # Get phase history for this plant
    phase_query = select(PhaseHistory).where(
        PhaseHistory.plant_id == plant.id
    ).order_by(PhaseHistory.started_at.asc())

    phase_result = await session.execute(phase_query)
    phases = phase_result.scalars().all()

    # Convert to serializable format
    phase_history = [
        {
            "phase": phase.phase,
            "started_at": phase.started_at.isoformat(),
            "ended_at": phase.ended_at.isoformat() if phase.ended_at else None
        }
        for phase in phases
    ]

    # Convert logs to serializable format
    from app.schemas import PlantDailyLogRead
    from pydantic import BaseModel

    logs_serialized = [
        {
            "id": log.id,
            "plant_id": log.plant_id,
            "log_date": log.log_date.isoformat(),
            "ph_min": log.ph_min,
            "ph_max": log.ph_max,
            "ph_avg": log.ph_avg,
            "ec_min": log.ec_min,
            "ec_max": log.ec_max,
            "ec_avg": log.ec_avg,
            "tds_min": log.tds_min,
            "tds_max": log.tds_max,
            "tds_avg": log.tds_avg,
            "water_temp_min": log.water_temp_min,
            "water_temp_max": log.water_temp_max,
            "water_temp_avg": log.water_temp_avg,
            "total_ph_up_ml": log.total_ph_up_ml,
            "total_ph_down_ml": log.total_ph_down_ml,
            "dosing_events_count": log.dosing_events_count,
            "co2_min": log.co2_min,
            "co2_max": log.co2_max,
            "co2_avg": log.co2_avg,
            "air_temp_min": log.air_temp_min,
            "air_temp_max": log.air_temp_max,
            "air_temp_avg": log.air_temp_avg,
            "humidity_min": log.humidity_min,
            "humidity_max": log.humidity_max,
            "humidity_avg": log.humidity_avg,
            "vpd_min": log.vpd_min,
            "vpd_max": log.vpd_max,
            "vpd_avg": log.vpd_avg,
            "total_light_seconds": log.total_light_seconds,
            "light_cycles_count": log.light_cycles_count,
            "longest_light_period_seconds": log.longest_light_period_seconds,
            "shortest_light_period_seconds": log.shortest_light_period_seconds,
            "hydro_device_id": log.hydro_device_id,
            "env_device_id": log.env_device_id,
            "readings_count": log.readings_count,
            "created_at": log.created_at.isoformat(),
            "updated_at": log.updated_at.isoformat()
        }
        for log in logs
    ]

    return {
        "logs": logs_serialized,
        "phase_history": phase_history
    }


# Environment Sensor Latest Data (for dashboard)

@router.get("/api/devices/{device_id}/environment/latest")
async def get_latest_environment_data(
    device_id: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get the latest environment sensor reading from cache."""
    # Verify device exists and user has access
    result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    # Check ownership or shared access
    if device.user_id != user.id:
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

    # Check for real-time cached data
    cached_data = environment_cache.get(device_id)
    if cached_data:
        return {
            "device_id": device_id,
            "has_data": True,
            "is_online": device.is_online,
            "last_seen": device.last_seen,
            "firmware_version": cached_data.get("firmware_version"),
            "use_fahrenheit": cached_data.get("use_fahrenheit", False),
            "co2": cached_data.get("co2"),
            "temperature": cached_data.get("temperature"),
            "humidity": cached_data.get("humidity"),
            "vpd": cached_data.get("vpd"),
            "pressure": cached_data.get("pressure"),
            "altitude": cached_data.get("altitude"),
            "gas_resistance": cached_data.get("gas_resistance"),
            "air_quality_score": cached_data.get("air_quality_score"),
            "lux": cached_data.get("lux"),
            "ppfd": cached_data.get("ppfd"),
            "timestamp": cached_data.get("timestamp"),
            "cached_at": cached_data.get("cached_at"),
            "served_at": datetime.utcnow().isoformat(),
            "source": "realtime"
        }

    # No cached data
    settings = {}
    if device.settings:
        try:
            settings = json.loads(device.settings)
        except:
            settings = {}

    return {
        "device_id": device_id,
        "has_data": False,
        "is_online": device.is_online,
        "last_seen": device.last_seen,
        "use_fahrenheit": settings.get("use_fahrenheit", False)
    }


# Device Settings

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
        log_interval=settings.get("log_interval", 14400)
    )


# Daily Report Endpoint (Once-Daily Aggregated Data)

@router.post("/api/devices/{device_id}/daily-report")
async def receive_daily_report(
    device_id: str,
    report: EnvironmentDailyReport | HydroDailyReport,
    api_key: str = Query(...),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Receive daily aggregated report from device.

    Devices calculate min/max/avg for all sensor readings throughout the day,
    then post once daily during their assigned time slot.

    Data is written to PlantDailyLog for all plants associated with the device:
    - Hydro controller: Plants assigned to that specific device
    - Environment sensor: All plants in the same location as the sensor
    """
    print(f"[DAILY REPORT] Received report from device {device_id} for date {report.report_date}")

    # 1. Validate device exists and API key matches
    result = await session.execute(
        select(Device).where(Device.device_id == device_id, Device.api_key == api_key)
    )
    device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found - please re-pair")

    # Parse report date
    try:
        report_date_obj = datetime.strptime(report.report_date, "%Y-%m-%d").date()
    except Exception as e:
        raise HTTPException(400, f"Invalid report_date format (expected YYYY-MM-DD): {str(e)}")

    # 2. Get associated plants based on device type
    plants = []

    if device.device_type in ['hydro_controller', 'feeding_system', 'hydroponic_controller']:
        # Hydro controller: Get plants assigned to this device
        assignments_result = await session.execute(
            select(Plant)
            .join(DeviceAssignment, DeviceAssignment.plant_id == Plant.id)
            .where(
                DeviceAssignment.device_id == device.id,
                DeviceAssignment.removed_at.is_(None)  # Only active assignments
            )
        )
        plants = assignments_result.scalars().all()
        print(f"[DAILY REPORT] Hydro controller - found {len(plants)} assigned plants")

    elif device.device_type == 'environmental':
        # Environment sensor: Get all plants assigned to devices in the same location
        if device.location_id is None:
            print(f"[DAILY REPORT] Environment sensor has no location assigned - no plants to update")
            return {
                "status": "success",
                "message": "Device has no location assigned",
                "plants_updated": 0
            }

        # Get all plants assigned to devices in the same location as the environment sensor
        plants_result = await session.execute(
            select(Plant)
            .join(DeviceAssignment, DeviceAssignment.plant_id == Plant.id)
            .join(Device, DeviceAssignment.device_id == Device.id)
            .where(
                Device.location_id == device.location_id,
                DeviceAssignment.removed_at.is_(None),  # Only active assignments
                Plant.end_date.is_(None)  # Only active plants
            )
        )
        plants = plants_result.scalars().all()
        print(f"[DAILY REPORT] Environment sensor - found {len(plants)} plants in location {device.location_id}")

    else:
        raise HTTPException(400, f"Device type '{device.device_type}' does not support daily reports")

    if not plants:
        print(f"[DAILY REPORT] No plants to update for device {device_id}")
        return {
            "status": "success",
            "message": "No active plants associated with device",
            "plants_updated": 0
        }

    # 3. For each plant, write/update PlantDailyLog
    for plant in plants:
        # Get or create today's log entry for this plant
        log_result = await session.execute(
            select(PlantDailyLog).where(
                PlantDailyLog.plant_id == plant.id,
                PlantDailyLog.log_date == report_date_obj
            )
        )
        log = log_result.scalars().first()

        if not log:
            # Create new daily log entry
            log = PlantDailyLog(
                plant_id=plant.id,
                log_date=report_date_obj,
                readings_count=0
            )
            session.add(log)
            await session.flush()  # Get the log ID

        # Update with report data based on report type
        if isinstance(report, EnvironmentDailyReport):
            # Environment sensor data
            log.env_device_id = device.id
            log.last_env_reading = datetime.utcnow()

            # CO2
            log.co2_min = report.co2_min
            log.co2_max = report.co2_max
            log.co2_avg = report.co2_avg

            # Temperature (stored as air_temp in PlantDailyLog)
            log.air_temp_min = report.temperature_min
            log.air_temp_max = report.temperature_max
            log.air_temp_avg = report.temperature_avg

            # Humidity
            log.humidity_min = report.humidity_min
            log.humidity_max = report.humidity_max
            log.humidity_avg = report.humidity_avg

            # VPD
            log.vpd_min = report.vpd_min
            log.vpd_max = report.vpd_max
            log.vpd_avg = report.vpd_avg

            # Light events (accumulate aggregates and store events - supports chunked reports)
            if report.light_events:
                total_seconds = sum(event.duration_seconds for event in report.light_events)
                durations = [event.duration_seconds for event in report.light_events]

                # Accumulate totals (handle chunked reports by adding to existing values)
                log.total_light_seconds = (log.total_light_seconds or 0) + total_seconds
                log.light_cycles_count = (log.light_cycles_count or 0) + len(report.light_events)

                # Update min/max durations (keep best values across all chunks)
                if durations:
                    chunk_max = max(durations)
                    chunk_min = min(durations)

                    if log.longest_light_period_seconds is None:
                        log.longest_light_period_seconds = chunk_max
                    else:
                        log.longest_light_period_seconds = max(log.longest_light_period_seconds, chunk_max)

                    if log.shortest_light_period_seconds is None:
                        log.shortest_light_period_seconds = chunk_min
                    else:
                        log.shortest_light_period_seconds = min(log.shortest_light_period_seconds, chunk_min)

                # Store individual light events
                for event in report.light_events:
                    try:
                        start_time = datetime.fromisoformat(event.start.replace('Z', '+00:00'))
                        end_time = datetime.fromisoformat(event.end.replace('Z', '+00:00'))

                        light_event = LightEvent(
                            plant_id=plant.id,
                            device_id=device.id,
                            event_date=report_date_obj,
                            start_time=start_time,
                            end_time=end_time,
                            duration_seconds=event.duration_seconds
                        )
                        session.add(light_event)
                    except Exception as e:
                        print(f"[DAILY REPORT] Error storing light event for plant {plant.plant_id}: {str(e)}")

            # Update readings count
            log.readings_count = report.readings_count

            print(f"[DAILY REPORT] Updated environment data for plant {plant.plant_id}")

        elif isinstance(report, HydroDailyReport):
            # Hydro controller data
            log.hydro_device_id = device.id
            log.last_hydro_reading = datetime.utcnow()

            # pH
            log.ph_min = report.ph_min
            log.ph_max = report.ph_max
            log.ph_avg = report.ph_avg

            # EC
            log.ec_min = report.ec_min
            log.ec_max = report.ec_max
            log.ec_avg = report.ec_avg

            # Water Temperature
            log.water_temp_min = report.water_temp_min
            log.water_temp_max = report.water_temp_max
            log.water_temp_avg = report.water_temp_avg

            # Air Temperature (if hydro controller has air temp sensor)
            if report.air_temp_min is not None:
                log.air_temp_min = report.air_temp_min
                log.air_temp_max = report.air_temp_max
                log.air_temp_avg = report.air_temp_avg

            # Update readings count
            log.readings_count = report.readings_count

            print(f"[DAILY REPORT] Updated hydro data for plant {plant.plant_id}")

            # 4. Log dosing events
            for event in report.dosing_events:
                try:
                    event_timestamp = date_parser.isoparse(event.timestamp)
                    event_date = event_timestamp.date()

                    # Create dosing event record
                    dosing = DosingEvent(
                        plant_id=plant.id,
                        device_id=device.id,
                        event_date=event_date,
                        timestamp=event_timestamp,
                        dosing_type=event.type,
                        amount_ml=event.amount_ml
                    )
                    session.add(dosing)

                    # Update totals in PlantDailyLog
                    if event.type == 'ph_up':
                        log.total_ph_up_ml = (log.total_ph_up_ml or 0) + event.amount_ml
                    elif event.type == 'ph_down':
                        log.total_ph_down_ml = (log.total_ph_down_ml or 0) + event.amount_ml

                    log.dosing_events_count = (log.dosing_events_count or 0) + 1

                except Exception as e:
                    print(f"[DAILY REPORT] Error parsing dosing event: {e}")
                    # Continue with other events

            if len(report.dosing_events) > 0:
                print(f"[DAILY REPORT] Logged {len(report.dosing_events)} dosing events for plant {plant.plant_id}")

        log.updated_at = datetime.utcnow()

    await session.commit()

    print(f"[DAILY REPORT] Successfully updated {len(plants)} plants for device {device_id}")

    return {
        "status": "success",
        "plants_updated": len(plants),
        "report_date": report.report_date
    }
