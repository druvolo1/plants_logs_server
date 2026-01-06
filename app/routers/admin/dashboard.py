# app/routers/admin/dashboard.py
"""
Admin dashboard stats API endpoints.
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import User, Device, Plant, PlantDailyLog, Location

router = APIRouter()


def _get_current_admin():
    from app.main import current_admin
    return current_admin


def _get_db():
    from app.main import get_db
    return get_db


@router.get("/api/dashboard/stats")
async def get_dashboard_stats(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Get dashboard statistics"""
    # Users
    total_users = await session.execute(select(func.count(User.id)))
    pending_users = await session.execute(select(func.count(User.id)).where(User.is_active == False))

    # Devices
    total_devices = await session.execute(select(func.count(Device.id)))
    online_devices = await session.execute(select(func.count(Device.id)).where(Device.is_online == True))

    # Plants
    total_plants = await session.execute(select(func.count(Plant.id)))
    active_plants = await session.execute(select(func.count(Plant.id)).where(Plant.end_date.is_(None)))

    # Locations
    total_locations = await session.execute(select(func.count(Location.id)))

    # Logs
    total_plant_daily_logs = await session.execute(select(func.count(PlantDailyLog.id)))

    return {
        "users": {
            "total": total_users.scalar() or 0,
            "pending": pending_users.scalar() or 0
        },
        "devices": {
            "total": total_devices.scalar() or 0,
            "online": online_devices.scalar() or 0
        },
        "plants": {
            "total": total_plants.scalar() or 0,
            "active": active_plants.scalar() or 0
        },
        "locations": total_locations.scalar() or 0,
        "logs": {
            "plant_daily_logs": total_plant_daily_logs.scalar() or 0,
            "log_entries": 0,  # Legacy, removed
            "environment_logs": 0  # Legacy, removed
        }
    }


@router.get("/api/dashboard/alerts")
async def get_dashboard_alerts(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Get system alerts"""
    alerts = []

    # Check for pending users
    pending_result = await session.execute(
        select(func.count(User.id)).where(User.is_active == False)
    )
    pending_count = pending_result.scalar() or 0
    if pending_count > 0:
        alerts.append({
            "level": "warning",
            "title": f"{pending_count} user(s) pending approval",
            "description": "New users are waiting for account activation"
        })

    # Check for offline devices that were recently online
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    offline_result = await session.execute(
        select(func.count(Device.id)).where(
            Device.is_online == False,
            Device.last_seen >= one_hour_ago
        )
    )
    recently_offline = offline_result.scalar() or 0
    if recently_offline > 0:
        alerts.append({
            "level": "error",
            "title": f"{recently_offline} device(s) went offline recently",
            "description": "These devices were online in the past hour but are now offline"
        })

    # Check for devices needing firmware updates
    try:
        from app.models import Firmware
        from app.routers.logs import environment_cache

        # Get latest firmware versions
        firmware_result = await session.execute(
            select(Firmware).where(Firmware.is_latest == True)
        )
        latest_firmwares = {fw.device_type: fw.version for fw in firmware_result.scalars().all()}

        # Count devices that may need updates
        outdated_count = 0
        for device_id, cache_data in environment_cache.items():
            fw_version = cache_data.get("firmware_version")
            if fw_version and latest_firmwares.get("environmental"):
                if fw_version != latest_firmwares["environmental"]:
                    outdated_count += 1

        if outdated_count > 0:
            alerts.append({
                "level": "warning",
                "title": f"{outdated_count} device(s) have outdated firmware",
                "description": "Consider updating these devices to the latest firmware"
            })
    except Exception:
        pass

    return alerts


@router.get("/api/dashboard/activity")
async def get_dashboard_activity(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Get recent activity feed"""
    activities = []

    # Recent user registrations (last 5)
    recent_users = await session.execute(
        select(User)
        .where(User.created_at.isnot(None))
        .order_by(User.created_at.desc())
        .limit(5)
    )
    for user in recent_users.scalars().all():
        activities.append({
            "type": "user",
            "message": f"User registered: {user.email}",
            "timestamp": user.created_at.isoformat() + 'Z' if user.created_at else None
        })

    # Recent device connections (last 10)
    recent_devices = await session.execute(
        select(Device, User.email)
        .join(User, Device.user_id == User.id)
        .where(Device.last_seen.isnot(None))
        .order_by(Device.last_seen.desc())
        .limit(10)
    )
    for device, email in recent_devices.all():
        activities.append({
            "type": "device",
            "message": f"{device.name or device.device_id[:8]} connected ({email})",
            "timestamp": device.last_seen.isoformat() + 'Z' if device.last_seen else None
        })

    # Sort by timestamp and return top 15
    activities.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    return activities[:15]


@router.get("/api/dashboard/device-status")
async def get_dashboard_device_status(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Get device status breakdown"""
    # Online/offline counts
    online_result = await session.execute(
        select(func.count(Device.id)).where(Device.is_online == True)
    )
    offline_result = await session.execute(
        select(func.count(Device.id)).where(Device.is_online == False)
    )

    # By device type
    type_result = await session.execute(
        select(Device.device_type, Device.is_online, func.count(Device.id))
        .group_by(Device.device_type, Device.is_online)
    )

    by_type = {}
    for device_type, is_online, count in type_result.all():
        dtype = device_type or "unknown"
        if dtype not in by_type:
            by_type[dtype] = {"online": 0, "offline": 0}
        if is_online:
            by_type[dtype]["online"] = count
        else:
            by_type[dtype]["offline"] = count

    return {
        "online": online_result.scalar() or 0,
        "offline": offline_result.scalar() or 0,
        "by_type": by_type
    }


@router.get("/api/dashboard/firmware-status")
async def get_dashboard_firmware_status(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Get firmware deployment status"""
    try:
        from app.models import Firmware
        from app.routers.logs import environment_cache

        # Get latest firmware by device type
        firmware_result = await session.execute(
            select(Firmware).where(Firmware.is_latest == True)
        )

        device_types = []
        for fw in firmware_result.scalars().all():
            # Count devices with this firmware
            devices_result = await session.execute(
                select(func.count(Device.id)).where(Device.device_type == fw.device_type)
            )
            total_devices = devices_result.scalar() or 0

            # Check cached versions for environmental sensors
            up_to_date = 0
            need_update = 0

            if fw.device_type == "environmental":
                for device_id, cache_data in environment_cache.items():
                    fw_version = cache_data.get("firmware_version")
                    if fw_version == fw.version:
                        up_to_date += 1
                    elif fw_version:
                        need_update += 1

            device_types.append({
                "type": fw.device_type,
                "latest_version": fw.version,
                "total_devices": total_devices,
                "devices_up_to_date": up_to_date,
                "devices_need_update": need_update
            })

        return {"device_types": device_types}
    except Exception as e:
        return {"device_types": [], "error": str(e)}


@router.get("/api/dashboard/recent-users")
async def get_dashboard_recent_users(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Get recent users with device counts"""
    users_result = await session.execute(
        select(User, func.count(Device.id).label("device_count"))
        .outerjoin(Device, User.id == Device.user_id)
        .group_by(User.id)
        .order_by(User.id.desc())
        .limit(10)
    )

    users = []
    for user, device_count in users_result.all():
        users.append({
            "id": user.id,
            "email": user.email,
            "is_active": user.is_active,
            "is_suspended": getattr(user, "is_suspended", False),
            "is_superuser": user.is_superuser,
            "device_count": device_count,
            "created_at": None
        })

    return users


@router.get("/api/dashboard/recent-devices")
async def get_dashboard_recent_devices(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Get recent devices"""
    devices_result = await session.execute(
        select(Device, User.email)
        .join(User, Device.user_id == User.id)
        .order_by(Device.id.desc())
        .limit(10)
    )

    devices = []
    for device, email in devices_result.all():
        devices.append({
            "device_id": device.device_id,
            "name": device.name,
            "owner_email": email,
            "device_type": device.device_type,
            "is_online": device.is_online,
            "last_seen": device.last_seen.isoformat() + 'Z' if device.last_seen else None
        })

    return devices


@router.get("/api/dashboard/device-posting-activity")
async def get_device_posting_activity(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Get device posting activity for the dashboard"""
    from app.models import DeviceAssignment

    # Get all devices with their posting stats
    devices_result = await session.execute(
        select(Device, User.email)
        .join(User, Device.user_id == User.id)
        .order_by(Device.device_type, Device.name)
    )

    device_activity = []
    today = datetime.utcnow().date()

    for device, owner_email in devices_result.all():
        # Count assigned plants
        assigned_plants_result = await session.execute(
            select(func.count(DeviceAssignment.id))
            .where(
                DeviceAssignment.device_id == device.id,
                DeviceAssignment.removed_at.is_(None)
            )
        )
        assigned_plants = assigned_plants_result.scalar() or 0

        # Count logs from this device today
        if device.device_type == 'hydro':
            logs_today_result = await session.execute(
                select(func.count(PlantDailyLog.id))
                .where(
                    PlantDailyLog.hydro_device_id == device.id,
                    PlantDailyLog.log_date == today
                )
            )
        elif device.device_type == 'environmental':
            logs_today_result = await session.execute(
                select(func.count(PlantDailyLog.id))
                .where(
                    PlantDailyLog.env_device_id == device.id,
                    PlantDailyLog.log_date == today
                )
            )
        else:
            logs_today_result = None

        logs_today = logs_today_result.scalar() if logs_today_result else 0

        # Get most recent log
        if device.device_type == 'hydro':
            last_log_result = await session.execute(
                select(PlantDailyLog.updated_at)
                .where(PlantDailyLog.hydro_device_id == device.id)
                .order_by(PlantDailyLog.updated_at.desc())
                .limit(1)
            )
        elif device.device_type == 'environmental':
            last_log_result = await session.execute(
                select(PlantDailyLog.updated_at)
                .where(PlantDailyLog.env_device_id == device.id)
                .order_by(PlantDailyLog.updated_at.desc())
                .limit(1)
            )
        else:
            last_log_result = None

        last_log = last_log_result.scalar() if last_log_result else None

        device_activity.append({
            "device_id": device.device_id,
            "name": device.name or device.device_id[:8],
            "device_type": device.device_type,
            "owner_email": owner_email,
            "is_online": device.is_online,
            "assigned_plants": assigned_plants,
            "logs_posted_today": logs_today,
            "last_post": last_log.isoformat() + 'Z' if last_log else None,
            "expected_posts": assigned_plants if device.device_type in ['hydro', 'environmental'] else 0
        })

    return device_activity


@router.get("/api/dashboard/plant-data-summary")
async def get_plant_data_summary(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Get plant data summary for the dashboard"""
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)

    # Active plants
    active_plants_result = await session.execute(
        select(func.count(Plant.id)).where(Plant.end_date.is_(None))
    )
    active_plants = active_plants_result.scalar() or 0

    # Plants with data today
    plants_with_data_today_result = await session.execute(
        select(func.count(func.distinct(PlantDailyLog.plant_id)))
        .where(PlantDailyLog.log_date == today)
    )
    plants_with_data_today = plants_with_data_today_result.scalar() or 0

    # Plants with data yesterday
    plants_with_data_yesterday_result = await session.execute(
        select(func.count(func.distinct(PlantDailyLog.plant_id)))
        .where(PlantDailyLog.log_date == yesterday)
    )
    plants_with_data_yesterday = plants_with_data_yesterday_result.scalar() or 0

    # Total daily logs
    total_logs_result = await session.execute(
        select(func.count(PlantDailyLog.id))
    )
    total_logs = total_logs_result.scalar() or 0

    # Logs from last 7 days
    week_ago = today - timedelta(days=7)
    logs_last_week_result = await session.execute(
        select(func.count(PlantDailyLog.id))
        .where(PlantDailyLog.log_date >= week_ago)
    )
    logs_last_week = logs_last_week_result.scalar() or 0

    # Plants missing data (active but no data yesterday)
    plants_missing_data_result = await session.execute(
        select(Plant.plant_id, Plant.name, User.email)
        .join(User, Plant.user_id == User.id)
        .outerjoin(
            PlantDailyLog,
            (PlantDailyLog.plant_id == Plant.id) & (PlantDailyLog.log_date == yesterday)
        )
        .where(
            Plant.end_date.is_(None),
            PlantDailyLog.id.is_(None)
        )
        .limit(10)
    )

    plants_missing = []
    for plant_id, name, owner_email in plants_missing_data_result.all():
        plants_missing.append({
            "plant_id": plant_id,
            "name": name,
            "owner": owner_email
        })

    return {
        "active_plants": active_plants,
        "plants_with_data_today": plants_with_data_today,
        "plants_with_data_yesterday": plants_with_data_yesterday,
        "data_coverage_yesterday": round((plants_with_data_yesterday / active_plants * 100) if active_plants > 0 else 0, 1),
        "total_daily_logs": total_logs,
        "logs_last_week": logs_last_week,
        "plants_missing_data": plants_missing
    }
