# app/services/reports.py
"""
Plant report generation service.

Handles both live reports (real-time aggregation from device data) and
frozen reports (generated when a plant is finished).
"""
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Plant, Device, DeviceAssignment, DeviceLink,
    LogEntry, EnvironmentLog, PhaseHistory, PlantReport
)


async def get_plant_data(
    session: AsyncSession,
    plant: Plant,
    include_raw: bool = True
) -> Dict[str, Any]:
    """
    Gather all data associated with a plant via DeviceAssignment history.

    Args:
        session: Database session
        plant: The plant to gather data for
        include_raw: Whether to include raw data points (True for frozen reports)

    Returns:
        Dictionary containing raw_data and aggregated_stats
    """
    # Get all device assignments for this plant
    assignments_result = await session.execute(
        select(DeviceAssignment, Device)
        .join(Device, DeviceAssignment.device_id == Device.id)
        .where(DeviceAssignment.plant_id == plant.id)
        .order_by(DeviceAssignment.assigned_at)
    )
    assignments = assignments_result.all()

    # Collect all feeding logs from assigned devices during assignment periods
    feeding_logs = []
    environment_logs = []
    device_assignments_data = []
    linked_devices_data = []

    for assignment, device in assignments:
        assign_start = assignment.assigned_at
        assign_end = assignment.removed_at or datetime.utcnow()

        # Record assignment info
        device_assignments_data.append({
            "device_id": device.device_id,
            "device_name": device.name,
            "assigned_at": assign_start.isoformat(),
            "removed_at": assignment.removed_at.isoformat() if assignment.removed_at else None
        })

        # Get feeding logs (sensor + dosing) from this device during assignment period
        logs_result = await session.execute(
            select(LogEntry).where(
                LogEntry.device_id == device.id,
                LogEntry.timestamp >= assign_start,
                LogEntry.timestamp <= assign_end
            ).order_by(LogEntry.timestamp)
        )

        for log in logs_result.scalars().all():
            feeding_logs.append({
                "id": log.id,
                "device_id": device.device_id,
                "event_type": log.event_type,
                "sensor_name": log.sensor_name,
                "value": log.value,
                "dose_type": log.dose_type,
                "dose_amount_ml": log.dose_amount_ml,
                "timestamp": log.timestamp.isoformat()
            })

        # Get linked environmental devices for this feeding system during assignment period
        links_result = await session.execute(
            select(DeviceLink, Device)
            .join(Device, DeviceLink.child_device_id == Device.id)
            .where(
                DeviceLink.parent_device_id == device.id,
                DeviceLink.created_at <= assign_end,
                # Include links that were active during assignment
                # (removed_at is NULL or removed_at > assign_start)
                ((DeviceLink.removed_at == None) | (DeviceLink.removed_at > assign_start))
            )
        )

        for link, linked_device in links_result.all():
            link_start = max(link.created_at, assign_start)
            link_end = min(link.removed_at or assign_end, assign_end)

            linked_devices_data.append({
                "parent_device_id": device.device_id,
                "child_device_id": linked_device.device_id,
                "child_device_name": linked_device.name,
                "link_type": link.link_type,
                "linked_at": link_start.isoformat(),
                "unlinked_at": link_end.isoformat() if link.removed_at and link.removed_at <= assign_end else None
            })

            # Get environment logs from linked device during overlap period
            env_result = await session.execute(
                select(EnvironmentLog).where(
                    EnvironmentLog.device_id == linked_device.id,
                    EnvironmentLog.timestamp >= link_start,
                    EnvironmentLog.timestamp <= link_end
                ).order_by(EnvironmentLog.timestamp)
            )

            for env_log in env_result.scalars().all():
                environment_logs.append({
                    "id": env_log.id,
                    "device_id": linked_device.device_id,
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
                    "timestamp": env_log.timestamp.isoformat()
                })

    # Get phase history
    phase_result = await session.execute(
        select(PhaseHistory)
        .where(PhaseHistory.plant_id == plant.id)
        .order_by(PhaseHistory.started_at)
    )
    phase_history = []
    for phase in phase_result.scalars().all():
        phase_history.append({
            "phase": phase.phase,
            "started_at": phase.started_at.isoformat(),
            "ended_at": phase.ended_at.isoformat() if phase.ended_at else None
        })

    # Build raw data structure
    raw_data = {
        "feeding_logs": feeding_logs if include_raw else [],
        "environment_logs": environment_logs if include_raw else [],
        "phase_history": phase_history,
        "device_assignments": device_assignments_data,
        "linked_devices": linked_devices_data
    }

    # Calculate aggregated statistics
    aggregated_stats = calculate_aggregated_stats(feeding_logs, environment_logs, phase_history)

    return {
        "raw_data": raw_data,
        "aggregated_stats": aggregated_stats
    }


def calculate_aggregated_stats(
    feeding_logs: List[Dict],
    environment_logs: List[Dict],
    phase_history: List[Dict]
) -> Dict[str, Any]:
    """
    Calculate aggregated statistics from raw data.
    """
    stats = {}

    # Sensor statistics (pH, EC, etc.)
    sensor_values = {}
    for log in feeding_logs:
        if log["event_type"] == "sensor" and log["sensor_name"] and log["value"] is not None:
            sensor_name = log["sensor_name"]
            if sensor_name not in sensor_values:
                sensor_values[sensor_name] = []
            sensor_values[sensor_name].append(log["value"])

    for sensor_name, values in sensor_values.items():
        if values:
            stats[sensor_name] = {
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "avg": round(sum(values) / len(values), 2),
                "readings_count": len(values)
            }

    # Dosing statistics
    total_ph_up_ml = 0.0
    total_ph_down_ml = 0.0
    dosing_events_count = 0

    for log in feeding_logs:
        if log["event_type"] == "dosing" and log["dose_amount_ml"]:
            dosing_events_count += 1
            if log["dose_type"] == "up":
                total_ph_up_ml += log["dose_amount_ml"]
            elif log["dose_type"] == "down":
                total_ph_down_ml += log["dose_amount_ml"]

    stats["total_ph_up_ml"] = round(total_ph_up_ml, 2)
    stats["total_ph_down_ml"] = round(total_ph_down_ml, 2)
    stats["dosing_events_count"] = dosing_events_count

    # Environment statistics
    env_fields = ["temperature", "humidity", "co2", "vpd", "lux", "ppfd"]
    for field in env_fields:
        values = [log[field] for log in environment_logs if log.get(field) is not None]
        if values:
            stats[f"env_{field}"] = {
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "avg": round(sum(values) / len(values), 2),
                "readings_count": len(values)
            }

    # Days in each phase
    days_in_phase = {}
    for phase in phase_history:
        phase_name = phase["phase"]
        start = datetime.fromisoformat(phase["started_at"])
        end = datetime.fromisoformat(phase["ended_at"]) if phase["ended_at"] else datetime.utcnow()
        days = (end - start).days
        days_in_phase[phase_name] = days_in_phase.get(phase_name, 0) + days

    stats["days_in_each_phase"] = days_in_phase

    return stats


async def generate_plant_report(session: AsyncSession, plant: Plant) -> PlantReport:
    """
    Generate and save a frozen PlantReport for a finished plant.

    This should be called when a plant is marked as finished.
    The report captures all raw data and aggregated stats at that moment.

    Args:
        session: Database session
        plant: The finished plant

    Returns:
        The created PlantReport
    """
    # Check if report already exists
    existing_result = await session.execute(
        select(PlantReport).where(PlantReport.plant_id == plant.id)
    )
    existing_report = existing_result.scalars().first()

    if existing_report:
        # Update existing report instead of creating new one
        return await update_plant_report(session, plant, existing_report)

    # Gather all plant data
    data = await get_plant_data(session, plant, include_raw=True)

    # Create the frozen report
    report = PlantReport(
        plant_id=plant.id,
        plant_name=plant.name,
        strain=plant.batch_number,  # Using batch_number as strain for now
        start_date=plant.start_date,
        end_date=plant.end_date,
        final_phase=plant.current_phase,
        raw_data=json.dumps(data["raw_data"]),
        aggregated_stats=json.dumps(data["aggregated_stats"])
    )

    session.add(report)
    await session.commit()
    await session.refresh(report)

    return report


async def update_plant_report(
    session: AsyncSession,
    plant: Plant,
    report: PlantReport
) -> PlantReport:
    """
    Update an existing plant report with fresh data.
    """
    data = await get_plant_data(session, plant, include_raw=True)

    report.plant_name = plant.name
    report.strain = plant.batch_number
    report.start_date = plant.start_date
    report.end_date = plant.end_date
    report.final_phase = plant.current_phase
    report.raw_data = json.dumps(data["raw_data"])
    report.aggregated_stats = json.dumps(data["aggregated_stats"])
    report.generated_at = datetime.utcnow()
    report.report_version += 1

    await session.commit()
    await session.refresh(report)

    return report


async def get_live_plant_report(session: AsyncSession, plant: Plant) -> Dict[str, Any]:
    """
    Generate a live (real-time) report for an active plant.

    This is used to show current stats for plants that are still growing.
    Does not save to database.

    Args:
        session: Database session
        plant: The active plant

    Returns:
        Dictionary with report data
    """
    # Check if there's a frozen report (plant was finished)
    frozen_result = await session.execute(
        select(PlantReport).where(PlantReport.plant_id == plant.id)
    )
    frozen_report = frozen_result.scalars().first()

    if frozen_report:
        # Return frozen report data
        return {
            "is_frozen": True,
            "generated_at": frozen_report.generated_at.isoformat(),
            "report_version": frozen_report.report_version,
            "plant_name": frozen_report.plant_name,
            "strain": frozen_report.strain,
            "start_date": frozen_report.start_date.isoformat() if frozen_report.start_date else None,
            "end_date": frozen_report.end_date.isoformat() if frozen_report.end_date else None,
            "final_phase": frozen_report.final_phase,
            "raw_data": json.loads(frozen_report.raw_data),
            "aggregated_stats": json.loads(frozen_report.aggregated_stats) if frozen_report.aggregated_stats else {}
        }

    # Generate live report
    data = await get_plant_data(session, plant, include_raw=True)

    return {
        "is_frozen": False,
        "generated_at": datetime.utcnow().isoformat(),
        "report_version": 0,
        "plant_name": plant.name,
        "strain": plant.batch_number,
        "start_date": plant.start_date.isoformat() if plant.start_date else None,
        "end_date": plant.end_date.isoformat() if plant.end_date else None,
        "final_phase": plant.current_phase,
        "raw_data": data["raw_data"],
        "aggregated_stats": data["aggregated_stats"]
    }
