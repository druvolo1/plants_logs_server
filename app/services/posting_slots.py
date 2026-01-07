# app/services/posting_slots.py
"""
Device posting time slot management service.

Distributes devices evenly across the configured posting window (default 1-6 AM)
to balance server load. Each device gets a unique time slot for daily data posting.
"""
from typing import Optional, List, Dict
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Device, DevicePostingSlot


def get_posting_window_config() -> Dict[str, int]:
    """Get the current posting window configuration."""
    from app.routers.admin.config import system_config
    return system_config["logging"]


def calculate_window_duration_minutes() -> int:
    """Calculate the posting window duration in minutes."""
    config = get_posting_window_config()
    start_hour = config["posting_window_start_hour"]
    end_hour = config["posting_window_end_hour"]
    return (end_hour - start_hour) * 60


async def get_device_posting_slot(device_id: int, session: AsyncSession) -> Optional[int]:
    """
    Get the assigned posting slot for a device.

    Args:
        device_id: Database ID of the device
        session: Database session

    Returns:
        Assigned minute offset (0-299 for 5-hour window), or None if not assigned
    """
    result = await session.execute(
        select(DevicePostingSlot.assigned_minute)
        .where(DevicePostingSlot.device_id == device_id)
    )
    slot = result.scalar_one_or_none()
    return slot


async def get_all_assigned_slots(session: AsyncSession) -> List[int]:
    """
    Get all currently assigned posting slots.

    Returns:
        List of assigned minute offsets
    """
    result = await session.execute(
        select(DevicePostingSlot.assigned_minute)
        .order_by(DevicePostingSlot.assigned_minute)
    )
    return list(result.scalars().all())


async def count_devices_needing_slots(session: AsyncSession) -> int:
    """
    Count devices that should have posting slots.
    Only counts hydro_controller, hydroponic_controller, and environmental device types.

    Returns:
        Number of devices that need slots
    """
    result = await session.execute(
        select(func.count(Device.id))
        .where(Device.device_type.in_(['hydro_controller', 'hydroponic_controller', 'environmental']))
    )
    return result.scalar() or 0


def find_best_slot(
    assigned_slots: List[int],
    window_duration: int,
    target_device_count: int
) -> int:
    """
    Find the best available slot to minimize gaps between devices.

    Strategy:
    1. If no slots assigned yet, start at minute 0
    2. Otherwise, find the largest gap and place in the middle

    Args:
        assigned_slots: List of currently assigned minute offsets (sorted)
        window_duration: Total window duration in minutes
        target_device_count: Total number of devices that will need slots

    Returns:
        Best available minute offset
    """
    if not assigned_slots:
        # First device - start at the beginning
        return 0

    # Calculate ideal spacing between devices
    ideal_spacing = window_duration / target_device_count

    # Find the largest gap between consecutive slots
    max_gap = 0
    best_slot = 0

    # Check gap before first slot
    if assigned_slots[0] > max_gap:
        max_gap = assigned_slots[0]
        best_slot = assigned_slots[0] // 2

    # Check gaps between consecutive slots
    for i in range(len(assigned_slots) - 1):
        gap = assigned_slots[i + 1] - assigned_slots[i]
        if gap > max_gap:
            max_gap = gap
            # Place in middle of gap
            best_slot = assigned_slots[i] + (gap // 2)

    # Check gap after last slot
    last_gap = window_duration - assigned_slots[-1]
    if last_gap > max_gap:
        max_gap = last_gap
        best_slot = assigned_slots[-1] + (last_gap // 2)

    return best_slot


async def assign_posting_slot(device_id: int, session: AsyncSession) -> int:
    """
    Assign a posting time slot to a device.

    Only assigns slots to hydro_controller, hydroponic_controller, and environmental device types.
    Other device types (valve_controller, etc.) don't post daily reports.

    Args:
        device_id: Database ID of the device
        session: Database session

    Returns:
        Assigned minute offset (0-299 for 5-hour window)

    Raises:
        ValueError: If device doesn't exist or already has a slot
    """
    # Verify device exists and needs a slot
    device_result = await session.execute(
        select(Device).where(Device.id == device_id)
    )
    device = device_result.scalar_one_or_none()

    if not device:
        raise ValueError(f"Device {device_id} not found")

    if device.device_type not in ['hydro_controller', 'hydroponic_controller', 'environmental']:
        raise ValueError(f"Device type '{device.device_type}' does not need a posting slot")

    # Check if already has a slot
    existing_slot = await get_device_posting_slot(device_id, session)
    if existing_slot is not None:
        raise ValueError(f"Device {device_id} already has posting slot {existing_slot}")

    # Get window configuration
    window_duration = calculate_window_duration_minutes()

    # Get all currently assigned slots
    assigned_slots = await get_all_assigned_slots(session)

    # Count total devices that will need slots
    total_devices = await count_devices_needing_slots(session)

    # Find best available slot
    new_slot = find_best_slot(assigned_slots, window_duration, total_devices)

    # Assign the slot
    posting_slot = DevicePostingSlot(
        device_id=device_id,
        assigned_minute=new_slot
    )
    session.add(posting_slot)
    await session.commit()

    print(f"[POSTING_SLOTS] Assigned slot {new_slot} to device {device_id} ({device.device_type})")

    return new_slot


async def rebalance_all_slots(session: AsyncSession) -> Dict[str, any]:
    """
    Rebalance all posting slots to evenly distribute devices across the window.

    This removes all existing slot assignments and redistributes devices
    evenly across the posting window.

    Args:
        session: Database session

    Returns:
        Dictionary with rebalancing results
    """
    # Get all devices that need posting slots
    devices_result = await session.execute(
        select(Device.id, Device.device_type)
        .where(Device.device_type.in_(['hydro_controller', 'hydroponic_controller', 'environmental']))
        .order_by(Device.id)
    )
    devices = devices_result.all()

    if not devices:
        return {
            "status": "success",
            "message": "No devices to rebalance",
            "devices_count": 0,
            "assignments": []
        }

    # Delete all existing slot assignments
    await session.execute(delete(DevicePostingSlot))

    # Calculate even distribution
    window_duration = calculate_window_duration_minutes()
    device_count = len(devices)
    slot_spacing = window_duration / device_count

    assignments = []
    for i, (device_id, device_type) in enumerate(devices):
        # Assign evenly spaced slots
        assigned_minute = int(i * slot_spacing)

        posting_slot = DevicePostingSlot(
            device_id=device_id,
            assigned_minute=assigned_minute
        )
        session.add(posting_slot)

        assignments.append({
            "device_id": device_id,
            "device_type": device_type,
            "assigned_minute": assigned_minute
        })

        print(f"[POSTING_SLOTS] Rebalanced: Device {device_id} ({device_type}) -> slot {assigned_minute}")

    await session.commit()

    return {
        "status": "success",
        "message": f"Rebalanced {device_count} devices across {window_duration} minute window",
        "devices_count": device_count,
        "window_duration": window_duration,
        "slot_spacing": slot_spacing,
        "assignments": assignments
    }


async def remove_posting_slot(device_id: int, session: AsyncSession) -> bool:
    """
    Remove a device's posting slot assignment.

    Args:
        device_id: Database ID of the device
        session: Database session

    Returns:
        True if slot was removed, False if no slot was assigned
    """
    result = await session.execute(
        delete(DevicePostingSlot).where(DevicePostingSlot.device_id == device_id)
    )
    await session.commit()

    if result.rowcount > 0:
        print(f"[POSTING_SLOTS] Removed posting slot for device {device_id}")
        return True
    return False
