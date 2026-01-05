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
    PlantDailyLog, PlantReport
)


async def get_purge_candidates(
    session: AsyncSession,
    retention_days: int = 30
) -> Dict[str, Any]:
    """
    Identify plant daily logs that can be safely purged.

    Data can be purged if:
    1. Plant is finished (has end_date)
    2. Plant has a frozen report (PlantReport exists)
    3. Report is older than retention_days buffer

    Args:
        session: Database session
        retention_days: Number of days to keep data after plant is finished with report

    Returns:
        Dictionary with purge candidate information
    """
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
    results = {
        "plant_daily_logs": [],
        "total_purgeable_logs": 0,
        "plants_analyzed": 0,
        "cutoff_date": cutoff_date.isoformat(),
        # Legacy fields for compatibility
        "log_entries": [],
        "environment_logs": [],
        "total_purgeable_log_entries": 0,
        "total_purgeable_environment_logs": 0,
        "devices_analyzed": 0
    }

    # Get all plants with frozen reports
    plants_with_reports_result = await session.execute(
        select(Plant, PlantReport)
        .join(PlantReport, Plant.id == PlantReport.plant_id)
        .where(Plant.end_date.isnot(None))  # Only finished plants
    )

    for plant, report in plants_with_reports_result.all():
        results["plants_analyzed"] += 1

        # Check if past retention buffer
        if not plant.end_date:
            continue

        retention_end = report.generated_at + timedelta(days=retention_days)

        if datetime.utcnow() > retention_end:
            # Past retention buffer - plant daily logs can be purged
            count_result = await session.execute(
                select(func.count(PlantDailyLog.id)).where(
                    PlantDailyLog.plant_id == plant.id
                )
            )
            count = count_result.scalar()

            if count > 0:
                results["plant_daily_logs"].append({
                    "plant_id": plant.plant_id,
                    "plant_name": plant.name,
                    "report_generated_at": report.generated_at.isoformat(),
                    "retention_end": retention_end.isoformat(),
                    "purgeable_count": count
                })
                results["total_purgeable_logs"] += count

    return results


async def purge_old_data(
    session: AsyncSession,
    retention_days: int = 30,
    dry_run: bool = True
) -> Dict[str, Any]:
    """
    Purge old plant daily logs that meet retention criteria.

    Args:
        session: Database session
        retention_days: Number of days to keep data after plant is finished with report
        dry_run: If True, only report what would be deleted without actually deleting

    Returns:
        Dictionary with purge results
    """
    candidates = await get_purge_candidates(session, retention_days)

    results = {
        "dry_run": dry_run,
        "retention_days": retention_days,
        "plant_daily_logs_deleted": 0,
        "log_entries_deleted": 0,  # Legacy
        "environment_logs_deleted": 0,  # Legacy
        "details": []
    }

    if dry_run:
        results["plant_daily_logs_deleted"] = candidates["total_purgeable_logs"]
        results["details"] = candidates["plant_daily_logs"]
        return results

    # Actually delete the data
    for entry in candidates["plant_daily_logs"]:
        plant_result = await session.execute(
            select(Plant).where(Plant.plant_id == entry["plant_id"])
        )
        plant = plant_result.scalars().first()

        if plant:
            delete_result = await session.execute(
                delete(PlantDailyLog).where(PlantDailyLog.plant_id == plant.id)
            )
            results["plant_daily_logs_deleted"] += delete_result.rowcount

    await session.commit()

    results["details"] = candidates["plant_daily_logs"]
    return results
