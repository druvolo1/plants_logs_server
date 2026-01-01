# app/routers/notifications.py
"""
Notification management endpoints for device alerts and notifications.
"""
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, or_, func
import time

from app.models import User, Device, Notification, NotificationSeverity, NotificationStatus, DeviceShare
from app.schemas.notification import (
    NotificationRead,
    NotificationCreate,
    NotificationUpdate,
    NotificationSummary,
    NotificationClearRequest,
)

router = APIRouter(tags=["notifications"])


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


async def verify_device_access(device_id: str, user: User, session: AsyncSession) -> bool:
    """Verify user has access to a device (owns it or has it shared)"""
    # Check ownership
    stmt = select(Device).where(
        and_(
            Device.device_id == device_id,
            Device.user_id == user.id
        )
    )
    result = await session.execute(stmt)
    device = result.scalar_one_or_none()

    if device:
        return True

    # Check if device is shared with user
    stmt = select(DeviceShare).join(Device, DeviceShare.device_id == Device.id).where(
        and_(
            Device.device_id == device_id,
            DeviceShare.shared_with_user_id == user.id,
            DeviceShare.is_active == True
        )
    )
    result = await session.execute(stmt)
    share = result.scalar_one_or_none()

    return share is not None


@router.get("/notifications", response_model=List[NotificationRead])
async def get_notifications(
    request: Request,
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    severity: Optional[NotificationSeverity] = Query(None, description="Filter by severity"),
    status: Optional[NotificationStatus] = Query(None, description="Filter by status"),
    active_only: bool = Query(False, description="Only return active notifications"),
    limit: int = Query(100, le=500, description="Maximum number of notifications to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Get notifications for user's devices.
    Returns notifications from all devices user owns or has access to.
    """
    effective_user = await get_effective_user(request, user, session)

    # Get all device IDs user has access to
    # Owned devices
    stmt = select(Device.device_id).where(Device.user_id == effective_user.id)
    result = await session.execute(stmt)
    owned_device_ids = [row[0] for row in result]

    # Shared devices
    stmt = select(Device.device_id).join(
        DeviceShare, DeviceShare.device_id == Device.id
    ).where(
        and_(
            DeviceShare.shared_with_user_id == effective_user.id,
            DeviceShare.is_active == True
        )
    )
    result = await session.execute(stmt)
    shared_device_ids = [row[0] for row in result]

    all_device_ids = list(set(owned_device_ids + shared_device_ids))

    if not all_device_ids:
        return []

    # Build query - join with Device to get device name
    # Use NULLIF to convert empty strings to NULL, then COALESCE to try name, system_name, then fall back to device_id
    from sqlalchemy import case
    device_display_name = func.coalesce(
        func.nullif(Device.name, ''),
        func.nullif(Device.system_name, ''),
        Device.device_id
    )

    conditions = [Notification.device_id.in_(all_device_ids)]

    if device_id:
        conditions.append(Notification.device_id == device_id)

    if severity:
        conditions.append(Notification.severity == severity)

    if status:
        conditions.append(Notification.status == status)
    elif active_only:
        conditions.append(Notification.status == NotificationStatus.ACTIVE)

    stmt = select(Notification, device_display_name).join(
        Device, Notification.device_id == Device.device_id
    ).where(and_(*conditions)).order_by(
        Notification.created_at.desc()
    ).limit(limit).offset(offset)

    result = await session.execute(stmt)
    rows = result.all()

    # Add device_name to each notification
    notifications = []
    for notif, device_name in rows:
        notif_dict = {
            "id": notif.id,
            "device_id": notif.device_id,
            "device_name": device_name,
            "alert_type": notif.alert_type,
            "alert_type_id": notif.alert_type_id,
            "severity": notif.severity,
            "status": notif.status,
            "source": notif.source,
            "message": notif.message,
            "first_occurrence": notif.first_occurrence,
            "last_occurrence": notif.last_occurrence,
            "cleared_at": notif.cleared_at,
            "created_at": notif.created_at,
            "updated_at": notif.updated_at,
        }
        notifications.append(notif_dict)

    return notifications


@router.get("/notifications/summary", response_model=NotificationSummary)
async def get_notifications_summary(
    request: Request,
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Get summary of notification counts for user's devices.
    """
    effective_user = await get_effective_user(request, user, session)

    # Get all device IDs user has access to
    stmt = select(Device.device_id).where(Device.user_id == effective_user.id)
    result = await session.execute(stmt)
    owned_device_ids = [row[0] for row in result]

    stmt = select(Device.device_id).join(
        DeviceShare, DeviceShare.device_id == Device.id
    ).where(
        and_(
            DeviceShare.shared_with_user_id == effective_user.id,
            DeviceShare.is_active == True
        )
    )
    result = await session.execute(stmt)
    shared_device_ids = [row[0] for row in result]

    all_device_ids = list(set(owned_device_ids + shared_device_ids))

    if not all_device_ids:
        return NotificationSummary(total=0, active=0, warnings=0, critical=0, info=0)

    # Build base condition
    base_condition = Notification.device_id.in_(all_device_ids)
    if device_id:
        base_condition = and_(base_condition, Notification.device_id == device_id)

    # Get total count
    stmt = select(func.count(Notification.id)).where(base_condition)
    result = await session.execute(stmt)
    total = result.scalar() or 0

    # Get active count
    stmt = select(func.count(Notification.id)).where(
        and_(base_condition, Notification.status == NotificationStatus.ACTIVE)
    )
    result = await session.execute(stmt)
    active = result.scalar() or 0

    # Get warning count (active only)
    stmt = select(func.count(Notification.id)).where(
        and_(
            base_condition,
            Notification.status == NotificationStatus.ACTIVE,
            Notification.severity == NotificationSeverity.WARNING
        )
    )
    result = await session.execute(stmt)
    warnings = result.scalar() or 0

    # Get critical count (active only)
    stmt = select(func.count(Notification.id)).where(
        and_(
            base_condition,
            Notification.status == NotificationStatus.ACTIVE,
            Notification.severity == NotificationSeverity.CRITICAL
        )
    )
    result = await session.execute(stmt)
    critical = result.scalar() or 0

    # Get info count (active only)
    stmt = select(func.count(Notification.id)).where(
        and_(
            base_condition,
            Notification.status == NotificationStatus.ACTIVE,
            Notification.severity == NotificationSeverity.INFO
        )
    )
    result = await session.execute(stmt)
    info = result.scalar() or 0

    return NotificationSummary(
        total=total,
        active=active,
        warnings=warnings,
        critical=critical,
        info=info
    )


@router.post("/notifications/{notification_id}/clear")
async def clear_notification(
    notification_id: int,
    request: Request,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    User clears a specific notification.
    This sends a clear command to the device and updates the database.
    """
    effective_user = await get_effective_user(request, user, session)

    # Get notification
    stmt = select(Notification).where(Notification.id == notification_id)
    result = await session.execute(stmt)
    notification = result.scalar_one_or_none()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    # Verify user has access to the device
    has_access = await verify_device_access(notification.device_id, effective_user, session)
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied")

    # Update notification status
    notification.status = NotificationStatus.USER_CLEARED
    if not notification.cleared_at:
        notification.cleared_at = int(time.time() * 1000)  # millis timestamp

    await session.commit()

    # Send clear command to device via WebSocket
    # This will be handled by the websocket module
    from app.routers.websocket import send_to_device
    await send_to_device(notification.device_id, {
        "type": "clear_notification",
        "notification_id": notification_id,
        "alert_type": notification.alert_type
    })

    return {"success": True, "message": "Notification cleared"}


@router.post("/notifications/clear-all")
async def clear_all_notifications(
    request: Request,
    device_id: Optional[str] = Query(None, description="Clear all for specific device, or all devices if not specified"),
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    User clears all active notifications.
    """
    effective_user = await get_effective_user(request, user, session)

    # Get all device IDs user has access to
    stmt = select(Device.device_id).where(Device.user_id == effective_user.id)
    result = await session.execute(stmt)
    owned_device_ids = [row[0] for row in result]

    stmt = select(Device.device_id).join(
        DeviceShare, DeviceShare.device_id == Device.id
    ).where(
        and_(
            DeviceShare.shared_with_user_id == effective_user.id,
            DeviceShare.is_active == True
        )
    )
    result = await session.execute(stmt)
    shared_device_ids = [row[0] for row in result]

    all_device_ids = list(set(owned_device_ids + shared_device_ids))

    if not all_device_ids:
        return {"success": True, "cleared_count": 0}

    # Build condition
    conditions = [
        Notification.device_id.in_(all_device_ids),
        Notification.status == NotificationStatus.ACTIVE
    ]

    if device_id:
        # Verify access to specific device
        has_access = await verify_device_access(device_id, effective_user, session)
        if not has_access:
            raise HTTPException(status_code=403, detail="Access denied")
        conditions.append(Notification.device_id == device_id)

    # Update all matching notifications
    current_millis = int(time.time() * 1000)
    stmt = update(Notification).where(and_(*conditions)).values(
        status=NotificationStatus.USER_CLEARED,
        cleared_at=current_millis
    )
    result = await session.execute(stmt)
    await session.commit()

    cleared_count = result.rowcount

    # Send clear_all command to device(s) via WebSocket
    from app.routers.websocket import send_to_device
    target_devices = [device_id] if device_id else all_device_ids
    for dev_id in target_devices:
        await send_to_device(dev_id, {
            "type": "clear_all_notifications"
        })

    return {"success": True, "cleared_count": cleared_count}


@router.delete("/notifications/cleanup")
async def cleanup_old_notifications(
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Admin endpoint to manually trigger cleanup of old cleared notifications.
    Removes notifications that have been cleared for more than 24 hours.
    """
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")

    # Calculate cutoff time (24 hours ago in millis)
    cutoff_millis = int((time.time() - 24 * 60 * 60) * 1000)

    # Delete cleared notifications older than 24 hours
    stmt = delete(Notification).where(
        and_(
            or_(
                Notification.status == NotificationStatus.SELF_CLEARED,
                Notification.status == NotificationStatus.USER_CLEARED
            ),
            Notification.cleared_at < cutoff_millis
        )
    )

    result = await session.execute(stmt)
    await session.commit()

    deleted_count = result.rowcount

    return {"success": True, "deleted_count": deleted_count}
