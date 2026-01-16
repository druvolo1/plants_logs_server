# app/services/reports.py
"""
Plant report generation service for plant-centric daily logs.

Simple and efficient - all data is already stored per-plant.
"""
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Plant, Device, PlantDailyLog, PhaseHistory, PlantReport
)


async def get_plant_data(
    session: AsyncSession,
    plant: Plant,
    include_raw: bool = True
) -> Dict[str, Any]:
    """
    Gather all data for a plant from plant-centric daily logs.
    Much simpler than old device-centric approach!

    Args:
        session: Database session
        plant: The plant to gather data for
        include_raw: Whether to include raw data points (True for frozen reports)

    Returns:
        Dictionary containing raw_data and aggregated_stats
    """
    # Simple query - get all daily logs for this plant
    # Filter to only include dates on or after plant start date
    logs_result = await session.execute(
        select(PlantDailyLog)
        .where(
            PlantDailyLog.plant_id == plant.id,
            PlantDailyLog.log_date >= plant.start_date
        )
        .order_by(PlantDailyLog.log_date)
    )
    logs = logs_result.scalars().all()

    # Convert logs to dictionaries
    daily_logs = []
    if include_raw:
        for log in logs:
            daily_logs.append({
                "log_date": log.log_date.isoformat(),
                # Hydro data
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
                # Environment data
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
                "lux_min": log.lux_min,
                "lux_max": log.lux_max,
                "lux_avg": log.lux_avg,
                "ppfd_min": log.ppfd_min,
                "ppfd_max": log.ppfd_max,
                "ppfd_avg": log.ppfd_avg,
                # Metadata
                "hydro_device_id": log.hydro_device_id,
                "env_device_id": log.env_device_id,
                "readings_count": log.readings_count
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
        "daily_logs": daily_logs if include_raw else [],
        "phase_history": phase_history
    }

    # Calculate aggregated statistics
    aggregated_stats = calculate_aggregated_stats(logs, phase_history)

    return {
        "raw_data": raw_data,
        "aggregated_stats": aggregated_stats
    }


def calculate_aggregated_stats(
    daily_logs: List[PlantDailyLog],
    phase_history: List[Dict]
) -> Dict[str, Any]:
    """
    Calculate aggregated statistics from daily logs.
    Data is already aggregated per day, so we just aggregate across days.
    """
    stats = {}

    if not daily_logs:
        return stats

    # Hydro sensor statistics (aggregate the daily averages)
    ph_values = [log.ph_avg for log in daily_logs if log.ph_avg is not None]
    if ph_values:
        stats["ph"] = {
            "min": round(min(ph_values), 2),
            "max": round(max(ph_values), 2),
            "avg": round(sum(ph_values) / len(ph_values), 2),
            "readings_count": len(ph_values)
        }

    ec_values = [log.ec_avg for log in daily_logs if log.ec_avg is not None]
    if ec_values:
        stats["ec"] = {
            "min": round(min(ec_values), 0),
            "max": round(max(ec_values), 0),
            "avg": round(sum(ec_values) / len(ec_values), 0),
            "readings_count": len(ec_values)
        }

    tds_values = [log.tds_avg for log in daily_logs if log.tds_avg is not None]
    if tds_values:
        stats["tds"] = {
            "min": round(min(tds_values), 0),
            "max": round(max(tds_values), 0),
            "avg": round(sum(tds_values) / len(tds_values), 0),
            "readings_count": len(tds_values)
        }

    water_temp_values = [log.water_temp_avg for log in daily_logs if log.water_temp_avg is not None]
    if water_temp_values:
        stats["water_temp"] = {
            "min": round(min(water_temp_values), 1),
            "max": round(max(water_temp_values), 1),
            "avg": round(sum(water_temp_values) / len(water_temp_values), 1),
            "readings_count": len(water_temp_values)
        }

    # Dosing statistics (sum across all days)
    total_ph_up_ml = sum(log.total_ph_up_ml or 0 for log in daily_logs)
    total_ph_down_ml = sum(log.total_ph_down_ml or 0 for log in daily_logs)
    dosing_events_count = sum(log.dosing_events_count or 0 for log in daily_logs)

    stats["total_ph_up_ml"] = round(total_ph_up_ml, 2)
    stats["total_ph_down_ml"] = round(total_ph_down_ml, 2)
    stats["dosing_events_count"] = dosing_events_count

    # Environment statistics (aggregate the daily averages)
    co2_values = [log.co2_avg for log in daily_logs if log.co2_avg is not None]
    if co2_values:
        stats["co2"] = {
            "min": round(min(co2_values), 0),
            "max": round(max(co2_values), 0),
            "avg": round(sum(co2_values) / len(co2_values), 0),
            "readings_count": len(co2_values)
        }

    air_temp_values = [log.air_temp_avg for log in daily_logs if log.air_temp_avg is not None]
    if air_temp_values:
        stats["air_temp"] = {
            "min": round(min(air_temp_values), 1),
            "max": round(max(air_temp_values), 1),
            "avg": round(sum(air_temp_values) / len(air_temp_values), 1),
            "readings_count": len(air_temp_values)
        }

    humidity_values = [log.humidity_avg for log in daily_logs if log.humidity_avg is not None]
    if humidity_values:
        stats["humidity"] = {
            "min": round(min(humidity_values), 1),
            "max": round(max(humidity_values), 1),
            "avg": round(sum(humidity_values) / len(humidity_values), 1),
            "readings_count": len(humidity_values)
        }

    vpd_values = [log.vpd_avg for log in daily_logs if log.vpd_avg is not None]
    if vpd_values:
        stats["vpd"] = {
            "min": round(min(vpd_values), 2),
            "max": round(max(vpd_values), 2),
            "avg": round(sum(vpd_values) / len(vpd_values), 2),
            "readings_count": len(vpd_values)
        }

    lux_values = [log.lux_avg for log in daily_logs if log.lux_avg is not None]
    if lux_values:
        stats["lux"] = {
            "min": round(min(lux_values), 0),
            "max": round(max(lux_values), 0),
            "avg": round(sum(lux_values) / len(lux_values), 0),
            "readings_count": len(lux_values)
        }

    ppfd_values = [log.ppfd_avg for log in daily_logs if log.ppfd_avg is not None]
    if ppfd_values:
        stats["ppfd"] = {
            "min": round(min(ppfd_values), 0),
            "max": round(max(ppfd_values), 0),
            "avg": round(sum(ppfd_values) / len(ppfd_values), 0),
            "readings_count": len(ppfd_values)
        }

    # Light hours statistics (sum across all days)
    total_light_seconds = sum(log.total_light_seconds or 0 for log in daily_logs)
    total_light_cycles = sum(log.light_cycles_count or 0 for log in daily_logs)
    days_with_light = len([log for log in daily_logs if log.total_light_seconds and log.total_light_seconds > 0])

    if total_light_seconds > 0:
        stats["total_light_hours"] = round(total_light_seconds / 3600, 2)
        stats["total_light_cycles"] = total_light_cycles
        stats["avg_light_hours_per_day"] = round((total_light_seconds / 3600) / days_with_light, 2) if days_with_light > 0 else 0
        stats["days_with_light_data"] = days_with_light

    # Days in each phase
    days_in_phase = {}
    for phase in phase_history:
        phase_name = phase["phase"]
        start = datetime.fromisoformat(phase["started_at"])
        end = datetime.fromisoformat(phase["ended_at"]) if phase["ended_at"] else datetime.utcnow()
        days = (end - start).days
        days_in_phase[phase_name] = days_in_phase.get(phase_name, 0) + days

    stats["days_in_each_phase"] = days_in_phase

    # Total days with data
    stats["total_days_logged"] = len(daily_logs)

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

    # After report is generated, purge the daily logs to save space
    await session.execute(
        select(PlantDailyLog).where(PlantDailyLog.plant_id == plant.id)
    )
    # Note: Actually deleting would be:
    # await session.execute(delete(PlantDailyLog).where(PlantDailyLog.plant_id == plant.id))
    # But keeping them for now until we verify reports work correctly

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
