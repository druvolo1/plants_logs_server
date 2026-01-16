# This is the corrected section for logs.py
# Replace lines 555-582 in app/routers/logs.py with this code

    # Parse date filters
    # CRITICAL: Always filter to exclude dates before plant start date
    # Extract just the date portion from plant.start_date for comparison
    from sqlalchemy import func

    # Convert datetime to date for proper comparison
    plant_start_date_only = plant.start_date.date() if hasattr(plant.start_date, 'date') else plant.start_date

    print(f"[DEBUG] Plant {plant.name} start_date: {plant.start_date}, start_date_only: {plant_start_date_only}")

    # Build query with proper date filtering
    query = select(PlantDailyLog).where(
        PlantDailyLog.plant_id == plant.id,
        PlantDailyLog.log_date >= plant_start_date_only
    )

    if start_date:
        try:
            start_dt = date_parser.isoparse(start_date).date()
            # Only use start_date filter if it's AFTER plant start date
            if start_dt > plant_start_date_only:
                query = query.where(PlantDailyLog.log_date >= start_dt)
        except Exception as e:
            raise HTTPException(400, f"Invalid start_date format: {str(e)}")

    if end_date:
        try:
            end_dt = date_parser.isoparse(end_date).date()
            query = query.where(PlantDailyLog.log_date <= end_dt)
        except Exception as e:
            raise HTTPException(400, f"Invalid end_date format: {str(e)}")

    # CRITICAL: Order by date ASCENDING (chronological: oldest first)
    query = query.order_by(PlantDailyLog.log_date.asc()).limit(limit)

    result = await session.execute(query)
    logs = result.scalars().all()

    # Debug: Print actual dates returned
    log_dates = [log.log_date for log in logs]
    print(f"[DEBUG] Returned log dates (should be chronological, starting from {plant_start_date_only}): {log_dates}")
