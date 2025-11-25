# app/services/data_retention.py
"""
Data retention and purge service.

Handles automatic cleanup of old device data after plant reports are generated
and the retention buffer period has passed.
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
from sqlalchemy import select, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Device, Plant, DeviceAssignment, DeviceLink,
    LogEntry, EnvironmentLog, PlantReport
)


async def get_purge_candidates(
    session: AsyncSession,
    retention_days: int = 30
) -> Dict[str, Any]:
    """
    Identify data that can be safely purged.

    Data can be purged if:
    1. It's older than the retention_days buffer
    2. All plants that were assigned to the device during that data's time range
       are finished AND have frozen reports generated

    Args:
        session: Database session
        retention_days: Number of days to keep data after all associated plants are finished

    Returns:
        Dictionary with purge candidate information
    """
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
    results = {
        "log_entries": [],
        "environment_logs": [],
        "total_purgeable_log_entries": 0,
        "total_purgeable_environment_logs": 0,
        "devices_analyzed": 0,
        "cutoff_date": cutoff_date.isoformat()
    }

    # Get all devices
    devices_result = await session.execute(select(Device))
    devices = devices_result.scalars().all()

    for device in devices:
        results["devices_analyzed"] += 1

        # Get the earliest date where we have log data
        log_range_result = await session.execute(
            select(func.min(LogEntry.timestamp), func.max(LogEntry.timestamp))
            .where(LogEntry.device_id == device.id)
        )
        log_range = log_range_result.first()

        if not log_range[0]:
            continue  # No log data for this device

        earliest_log = log_range[0]
        latest_log = log_range[1]

        # Get all plant assignments for this device
        assignments_result = await session.execute(
            select(DeviceAssignment, Plant)
            .join(Plant, DeviceAssignment.plant_id == Plant.id)
            .where(DeviceAssignment.device_id == device.id)
            .order_by(DeviceAssignment.assigned_at)
        )
        assignments = assignments_result.all()

        if not assignments:
            # No plant assignments - this data is orphaned
            # Can purge data older than cutoff
            purgeable_count = await session.execute(
                select(func.count(LogEntry.id)).where(
                    LogEntry.device_id == device.id,
                    LogEntry.timestamp < cutoff_date
                )
            )
            count = purgeable_count.scalar()
            if count > 0:
                results["log_entries"].append({
                    "device_id": device.device_id,
                    "device_name": device.name,
                    "reason": "orphaned_data",
                    "purgeable_count": count,
                    "earliest": earliest_log.isoformat(),
                    "cutoff": cutoff_date.isoformat()
                })
                results["total_purgeable_log_entries"] += count
            continue

        # For devices with assignments, check if all associated plants are finished
        # and have reports generated
        purgeable_ranges = []

        for assignment, plant in assignments:
            assign_start = assignment.assigned_at
            assign_end = assignment.removed_at or datetime.utcnow()

            # Check if plant is finished
            if not plant.end_date:
                # Plant is still active - can't purge any data in this range
                continue

            # Check if plant has a frozen report
            report_result = await session.execute(
                select(PlantReport).where(PlantReport.plant_id == plant.id)
            )
            report = report_result.scalars().first()

            if not report:
                # No report generated yet - can't purge
                continue

            # Plant is finished with report - check if past retention buffer
            retention_end = plant.end_date + timedelta(days=retention_days)

            if datetime.utcnow() > retention_end:
                # Past retention buffer - data in this range is purgeable
                purgeable_ranges.append((assign_start, assign_end, plant.name))

        # Count purgeable log entries based on ranges
        for range_start, range_end, plant_name in purgeable_ranges:
            count_result = await session.execute(
                select(func.count(LogEntry.id)).where(
                    LogEntry.device_id == device.id,
                    LogEntry.timestamp >= range_start,
                    LogEntry.timestamp <= range_end
                )
            )
            count = count_result.scalar()
            if count > 0:
                results["log_entries"].append({
                    "device_id": device.device_id,
                    "device_name": device.name,
                    "plant_name": plant_name,
                    "reason": "past_retention",
                    "purgeable_count": count,
                    "range_start": range_start.isoformat(),
                    "range_end": range_end.isoformat()
                })
                results["total_purgeable_log_entries"] += count

    # Check environment logs similarly
    env_devices_result = await session.execute(
        select(Device).where(Device.device_type == 'environmental')
    )
    env_devices = env_devices_result.scalars().all()

    for device in env_devices:
        # Get links to feeding systems
        links_result = await session.execute(
            select(DeviceLink, Device)
            .join(Device, DeviceLink.parent_device_id == Device.id)
            .where(DeviceLink.child_device_id == device.id)
        )
        links = links_result.all()

        if not links:
            # Orphaned env sensor - can purge old data
            purgeable_count = await session.execute(
                select(func.count(EnvironmentLog.id)).where(
                    EnvironmentLog.device_id == device.id,
                    EnvironmentLog.timestamp < cutoff_date
                )
            )
            count = purgeable_count.scalar()
            if count > 0:
                results["environment_logs"].append({
                    "device_id": device.device_id,
                    "device_name": device.name,
                    "reason": "orphaned_data",
                    "purgeable_count": count
                })
                results["total_purgeable_environment_logs"] += count

    return results


async def purge_old_data(
    session: AsyncSession,
    retention_days: int = 30,
    dry_run: bool = True
) -> Dict[str, Any]:
    """
    Purge old device data that meets retention criteria.

    Args:
        session: Database session
        retention_days: Number of days to keep data after all associated plants are finished
        dry_run: If True, only report what would be deleted without actually deleting

    Returns:
        Dictionary with purge results
    """
    candidates = await get_purge_candidates(session, retention_days)

    results = {
        "dry_run": dry_run,
        "retention_days": retention_days,
        "log_entries_deleted": 0,
        "environment_logs_deleted": 0,
        "details": []
    }

    if dry_run:
        results["log_entries_deleted"] = candidates["total_purgeable_log_entries"]
        results["environment_logs_deleted"] = candidates["total_purgeable_environment_logs"]
        results["details"] = candidates["log_entries"] + candidates["environment_logs"]
        return results

    # Actually delete the data
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    # Delete orphaned log entries (no plant assignments)
    for entry in candidates["log_entries"]:
        if entry["reason"] == "orphaned_data":
            device_result = await session.execute(
                select(Device).where(Device.device_id == entry["device_id"])
            )
            device = device_result.scalars().first()
            if device:
                delete_result = await session.execute(
                    delete(LogEntry).where(
                        LogEntry.device_id == device.id,
                        LogEntry.timestamp < cutoff_date
                    )
                )
                results["log_entries_deleted"] += delete_result.rowcount

        elif entry["reason"] == "past_retention":
            device_result = await session.execute(
                select(Device).where(Device.device_id == entry["device_id"])
            )
            device = device_result.scalars().first()
            if device:
                from dateutil import parser as date_parser
                range_start = date_parser.isoparse(entry["range_start"])
                range_end = date_parser.isoparse(entry["range_end"])

                delete_result = await session.execute(
                    delete(LogEntry).where(
                        LogEntry.device_id == device.id,
                        LogEntry.timestamp >= range_start,
                        LogEntry.timestamp <= range_end
                    )
                )
                results["log_entries_deleted"] += delete_result.rowcount

    # Delete orphaned environment logs
    for entry in candidates["environment_logs"]:
        if entry["reason"] == "orphaned_data":
            device_result = await session.execute(
                select(Device).where(Device.device_id == entry["device_id"])
            )
            device = device_result.scalars().first()
            if device:
                delete_result = await session.execute(
                    delete(EnvironmentLog).where(
                        EnvironmentLog.device_id == device.id,
                        EnvironmentLog.timestamp < cutoff_date
                    )
                )
                results["environment_logs_deleted"] += delete_result.rowcount

    await session.commit()

    results["details"] = candidates["log_entries"] + candidates["environment_logs"]
    return results
