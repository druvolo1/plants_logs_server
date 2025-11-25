# app/routers/devices.py
"""
Device management endpoints including CRUD, pairing, and sharing.
"""
from typing import List, Dict
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
import secrets

from app.models import User, Device, DeviceShare, DeviceLink, Plant, DeviceAssignment, Location
from app.schemas import (
    DeviceCreate,
    DeviceUpdate,
    DeviceRead,
    DevicePairRequest,
    DevicePairResponse,
    ShareCreate,
    ShareAccept,
    ShareUpdate,
    ShareRead,
    DeviceLinkCreate,
    DeviceLinkRead,
    AvailableDeviceForLinking,
    LinkedDeviceInfo,
)

router = APIRouter(prefix="/user/devices", tags=["devices"])
api_router = APIRouter(prefix="/api/devices", tags=["devices-api"])


def get_current_user_dependency():
    """Import and return current_user dependency"""
    from app.main import current_user
    return current_user


def get_db_dependency():
    """Import and return get_db dependency"""
    from app.main import get_db
    return get_db


# Temporary storage for pairing results (device_id -> pairing result)
# In production, use Redis or database with expiration
pairing_results = {}


async def generate_share_code(session: AsyncSession) -> str:
    """Generate a unique 10-character alphanumeric share code."""
    import string
    import random
    from app.models import LocationShare

    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.ascii_lowercase + string.digits, k=10))
        # Check if code already exists in both tables
        device_result = await session.execute(select(DeviceShare).where(DeviceShare.share_code == code))
        location_result = await session.execute(select(LocationShare).where(LocationShare.share_code == code))
        if not device_result.scalars().first() and not location_result.scalars().first():
            return code


# Device CRUD Endpoints

@router.post("", response_model=Dict[str, str])
async def add_device(
    device: DeviceCreate,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Add a new device"""
    existing = await session.execute(select(Device).where(Device.device_id == device.device_id))
    if existing.scalars().first():
        raise HTTPException(400, "Device ID already linked")

    api_key = secrets.token_hex(32)

    # Set default scope based on device type
    scope = device.scope
    if not scope:
        # Default scopes for different device types
        if device.device_type == 'environmental':
            scope = 'room'
        else:
            scope = 'plant'

    new_device = Device(
        device_id=device.device_id,
        api_key=api_key,
        name=device.name,
        device_type=device.device_type or 'feeding_system',
        scope=scope,
        location_id=device.location_id,
        user_id=user.id
    )
    session.add(new_device)
    await session.commit()
    await session.refresh(new_device)

    return {"api_key": api_key, "message": "Device added. Copy API key to Pi settings."}


@router.get("", response_model=List[DeviceRead])
async def list_devices(
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """List all devices owned by or shared with the user"""
    devices_list = []

    # Get owned devices
    owned_result = await session.execute(select(Device).where(Device.user_id == user.id))
    for device in owned_result.scalars().all():
        # Get active plant assignments
        assignments_result = await session.execute(
            select(DeviceAssignment, Plant)
            .join(Plant, DeviceAssignment.plant_id == Plant.id)
            .where(
                DeviceAssignment.device_id == device.id,
                DeviceAssignment.removed_at == None
            )
        )

        assigned_plants = []
        for assignment, plant in assignments_result.all():
            from app.schemas import AssignedPlantInfo
            assigned_plants.append(AssignedPlantInfo(
                plant_id=plant.plant_id,
                name=plant.name,
                current_phase=plant.current_phase
            ))

        # Get linked devices for feeding systems
        linked_devices = []
        if device.device_type == 'feeding_system':
            links_result = await session.execute(
                select(DeviceLink, Device)
                .join(Device, DeviceLink.child_device_id == Device.id)
                .where(DeviceLink.parent_device_id == device.id)
            )
            for link, child_device in links_result.all():
                linked_devices.append(LinkedDeviceInfo(
                    device_id=child_device.device_id,
                    name=child_device.name,
                    system_name=child_device.system_name,
                    device_type=child_device.device_type,
                    is_online=child_device.is_online,
                    link_type=link.link_type,
                    is_location_inherited=link.is_location_inherited
                ))

        devices_list.append(DeviceRead(
            id=device.id,
            device_id=device.device_id,
            name=device.name,
            system_name=device.system_name,
            device_type=device.device_type,
            scope=device.scope,
            location_id=device.location_id,
            is_online=device.is_online,
            last_seen=device.last_seen,
            is_owner=True,
            assigned_plants=assigned_plants,
            linked_devices=linked_devices
        ))

    # Get shared devices (accepted and active)
    shared_result = await session.execute(
        select(DeviceShare, Device)
        .join(Device, DeviceShare.device_id == Device.id)
        .where(
            DeviceShare.shared_with_user_id == user.id,
            DeviceShare.is_active == True,
            DeviceShare.accepted_at != None,
            DeviceShare.revoked_at == None,
            or_(DeviceShare.expires_at == None, DeviceShare.expires_at > datetime.utcnow())
        )
    )

    for share, device in shared_result.all():
        # Get owner info
        owner_result = await session.execute(select(User).where(User.id == share.owner_user_id))
        owner = owner_result.scalars().first()
        owner_email = owner.email if owner else "Unknown"

        # Get active plant assignments
        assignments_result = await session.execute(
            select(DeviceAssignment, Plant)
            .join(Plant, DeviceAssignment.plant_id == Plant.id)
            .where(
                DeviceAssignment.device_id == device.id,
                DeviceAssignment.removed_at == None
            )
        )

        assigned_plants = []
        for assignment, plant in assignments_result.all():
            from app.schemas import AssignedPlantInfo
            assigned_plants.append(AssignedPlantInfo(
                plant_id=plant.plant_id,
                name=plant.name,
                current_phase=plant.current_phase
            ))

        devices_list.append(DeviceRead(
            id=device.id,
            device_id=device.device_id,
            name=device.name,
            system_name=device.system_name,
            device_type=device.device_type,
            scope=device.scope,
            location_id=device.location_id,
            is_online=device.is_online,
            last_seen=device.last_seen,
            is_owner=False,
            permission_level=share.permission_level,
            shared_by_email=owner_email,
            assigned_plants=assigned_plants
        ))

    return devices_list


@router.put("/{device_id}")
async def update_device(
    device_id: str,
    device_update: DeviceUpdate,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Update device information"""
    result = await session.execute(select(Device).where(Device.device_id == device_id, Device.user_id == user.id))
    device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found or access denied")

    # Update fields if provided
    if device_update.name is not None:
        device.name = device_update.name
    if device_update.location_id is not None:
        device.location_id = device_update.location_id

    await session.commit()
    await session.refresh(device)

    return {"status": "success", "message": "Device updated"}


@router.delete("/{device_id}")
async def delete_device(
    device_id: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Delete a device"""
    # Load device with its related plants to allow proper cascade deletion
    result = await session.execute(
        select(Device).where(Device.device_id == device_id, Device.user_id == user.id)
    )
    device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    await session.delete(device)
    await session.commit()

    return {"status": "success", "message": "Device deleted"}


@router.get("/{device_id}/plants")
async def get_device_plants(
    device_id: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get all plants assigned to a device"""
    # Verify device exists and user has access
    result = await session.execute(select(Device).where(Device.device_id == device_id))
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

    # Get active plant assignments
    assignments_result = await session.execute(
        select(DeviceAssignment, Plant)
        .join(Plant, DeviceAssignment.plant_id == Plant.id)
        .where(
            DeviceAssignment.device_id == device.id,
            DeviceAssignment.removed_at == None
        )
    )

    plants_list = []
    for assignment, plant in assignments_result.all():
        plants_list.append({
            "plant_id": plant.plant_id,
            "name": plant.name,
            "current_phase": plant.current_phase,
            "status": plant.status,
            "assigned_at": assignment.assigned_at
        })

    return plants_list


# Device Sharing Endpoints

@router.post("/{device_id}/share", response_model=Dict[str, str])
async def create_device_share(
    device_id: str,
    share_data: ShareCreate,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Create a share code for a device"""
    # Verify user owns the device
    result = await session.execute(select(Device).where(Device.device_id == device_id, Device.user_id == user.id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(404, "Device not found or not owned by you")

    # Validate permission level
    if share_data.permission_level not in ['viewer', 'controller']:
        raise HTTPException(400, "Invalid permission level. Must be 'viewer' or 'controller'")

    # Generate unique share code
    share_code = await generate_share_code(session)

    # Create share with expiration (None for never expire)
    expires_at = None if share_data.expires_in_days is None else datetime.utcnow() + timedelta(days=share_data.expires_in_days)

    share = DeviceShare(
        device_id=device.id,
        owner_user_id=user.id,
        share_code=share_code,
        permission_level=share_data.permission_level,
        expires_at=expires_at,
        is_active=True
    )

    session.add(share)
    await session.commit()
    await session.refresh(share)

    return {"share_code": share_code, "expires_at": share.expires_at.isoformat() if share.expires_at else None}


@router.post("/accept-share", response_model=Dict[str, str])
async def accept_device_share(
    share_data: ShareAccept,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Accept a device share using a share code"""
    # Find the share by code
    result = await session.execute(
        select(DeviceShare).where(
            DeviceShare.share_code == share_data.share_code,
            DeviceShare.is_active == True,
            DeviceShare.accepted_at == None
        )
    )
    share = result.scalars().first()

    if not share:
        raise HTTPException(404, "Invalid or already accepted share code")

    # Check if expired (skip check if expires_at is None)
    if share.expires_at is not None and datetime.utcnow() > share.expires_at:
        share.is_active = False
        await session.commit()
        raise HTTPException(400, "Share code has expired")

    # Check if user is trying to share with themselves
    if share.owner_user_id == user.id:
        raise HTTPException(400, "You cannot accept your own share")

    # Accept the share
    share.shared_with_user_id = user.id
    share.accepted_at = datetime.utcnow()

    await session.commit()
    await session.refresh(share)

    # Get device info
    device_result = await session.execute(select(Device).where(Device.id == share.device_id))
    device = device_result.scalars().first()

    return {"status": "success", "device_id": device.device_id if device else "unknown", "device_name": device.name if device else "unknown"}


@router.get("/{device_id}/shares", response_model=List[ShareRead])
async def list_device_shares(
    device_id: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """List all shares for a device (owner only)"""
    # Verify ownership
    device_result = await session.execute(select(Device).where(Device.device_id == device_id, Device.user_id == user.id))
    device = device_result.scalars().first()
    if not device:
        raise HTTPException(404, "Device not found or not owned by you")

    # Get all active shares
    shares_result = await session.execute(
        select(DeviceShare).where(
            DeviceShare.device_id == device.id,
            DeviceShare.owner_user_id == user.id,
            DeviceShare.revoked_at == None
        )
    )

    shares_list = []
    for share in shares_result.scalars().all():
        shared_with_email = None
        if share.shared_with_user_id:
            user_result = await session.execute(select(User).where(User.id == share.shared_with_user_id))
            shared_user = user_result.scalars().first()
            shared_with_email = shared_user.email if shared_user else None

        shares_list.append(ShareRead(
            id=share.id,
            device_id=device.device_id,
            share_code=share.share_code,
            permission_level=share.permission_level,
            created_at=share.created_at,
            expires_at=share.expires_at,
            accepted_at=share.accepted_at,
            is_active=share.is_active,
            shared_with_email=shared_with_email
        ))

    return shares_list


@router.delete("/shares/{share_id}")
async def revoke_device_share(
    share_id: int,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Revoke a device share"""
    # Verify ownership and get share
    share_result = await session.execute(
        select(DeviceShare).where(
            DeviceShare.id == share_id,
            DeviceShare.owner_user_id == user.id
        )
    )
    share = share_result.scalars().first()

    if not share:
        raise HTTPException(404, "Share not found or access denied")

    # Mark as revoked
    share.revoked_at = datetime.utcnow()
    share.is_active = False

    await session.commit()

    return {"status": "success", "message": "Share revoked"}


@router.put("/shares/{share_id}/permission")
async def update_device_share_permission(
    share_id: int,
    share_data: ShareUpdate,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Update the permission level of a device share"""
    # Validate permission level
    if share_data.permission_level not in ['viewer', 'controller']:
        raise HTTPException(400, "Invalid permission level. Must be 'viewer' or 'controller'")

    # Find the share and verify ownership
    result = await session.execute(
        select(DeviceShare).where(
            DeviceShare.id == share_id,
            DeviceShare.owner_user_id == user.id
        )
    )
    share = result.scalars().first()

    if not share:
        raise HTTPException(404, "Share not found or not owned by you")

    # Update permission
    share.permission_level = share_data.permission_level

    await session.commit()

    return {"status": "success", "permission_level": share.permission_level}


# Device Linking Endpoints

@router.get("/{device_id}/available-links", response_model=List[AvailableDeviceForLinking])
async def get_available_devices_for_linking(
    device_id: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Get devices that can be linked to a feeding system.
    Only returns environmental sensors and valve controllers that the user owns.
    """
    # Verify user owns the parent device and it's a feeding_system
    result = await session.execute(
        select(Device).where(Device.device_id == device_id, Device.user_id == user.id)
    )
    parent_device = result.scalars().first()

    if not parent_device:
        raise HTTPException(404, "Device not found or not owned by you")

    if parent_device.device_type != 'feeding_system':
        raise HTTPException(400, "Only feeding systems can have linked devices")

    # Get all linkable devices (environmental and valve_controller) owned by user
    linkable_result = await session.execute(
        select(Device, Location)
        .outerjoin(Location, Device.location_id == Location.id)
        .where(
            Device.user_id == user.id,
            Device.device_type.in_(['environmental', 'valve_controller']),
            Device.id != parent_device.id
        )
    )

    # Get already linked device IDs
    linked_result = await session.execute(
        select(DeviceLink.child_device_id).where(DeviceLink.parent_device_id == parent_device.id)
    )
    already_linked_ids = {row[0] for row in linked_result.all()}

    available = []
    for device, location in linkable_result.all():
        if device.id not in already_linked_ids:
            available.append(AvailableDeviceForLinking(
                device_id=device.device_id,
                name=device.name,
                system_name=device.system_name,
                device_type=device.device_type,
                is_online=device.is_online,
                location_id=device.location_id,
                location_name=location.name if location else None,
                is_same_location=device.location_id == parent_device.location_id if parent_device.location_id else False
            ))

    return available


@router.get("/{device_id}/links", response_model=List[DeviceLinkRead])
async def get_device_links(
    device_id: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get all devices linked to a feeding system"""
    # Verify user owns the device
    result = await session.execute(
        select(Device).where(Device.device_id == device_id, Device.user_id == user.id)
    )
    parent_device = result.scalars().first()

    if not parent_device:
        raise HTTPException(404, "Device not found or not owned by you")

    # Get all links with child device info
    links_result = await session.execute(
        select(DeviceLink, Device)
        .join(Device, DeviceLink.child_device_id == Device.id)
        .where(DeviceLink.parent_device_id == parent_device.id)
    )

    links = []
    for link, child_device in links_result.all():
        links.append(DeviceLinkRead(
            id=link.id,
            link_type=link.link_type,
            is_location_inherited=link.is_location_inherited,
            created_at=link.created_at,
            child_device_id=child_device.device_id,
            child_device_name=child_device.name,
            child_device_system_name=child_device.system_name,
            child_device_type=child_device.device_type,
            child_device_is_online=child_device.is_online
        ))

    return links


@router.post("/{device_id}/links", response_model=DeviceLinkRead)
async def create_device_link(
    device_id: str,
    link_data: DeviceLinkCreate,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Link an environmental sensor or valve controller to a feeding system"""
    # Validate link type
    if link_data.link_type not in ['environmental', 'valve_controller']:
        raise HTTPException(400, "Invalid link type. Must be 'environmental' or 'valve_controller'")

    # Verify user owns the parent device and it's a feeding_system
    result = await session.execute(
        select(Device).where(Device.device_id == device_id, Device.user_id == user.id)
    )
    parent_device = result.scalars().first()

    if not parent_device:
        raise HTTPException(404, "Parent device not found or not owned by you")

    if parent_device.device_type != 'feeding_system':
        raise HTTPException(400, "Only feeding systems can have linked devices")

    # Find the child device
    child_result = await session.execute(
        select(Device).where(Device.device_id == link_data.child_device_id, Device.user_id == user.id)
    )
    child_device = child_result.scalars().first()

    if not child_device:
        raise HTTPException(404, "Child device not found or not owned by you")

    # Validate device type matches link type
    if link_data.link_type == 'environmental' and child_device.device_type != 'environmental':
        raise HTTPException(400, "Device is not an environmental sensor")
    if link_data.link_type == 'valve_controller' and child_device.device_type != 'valve_controller':
        raise HTTPException(400, "Device is not a valve controller")

    # Check if link already exists
    existing = await session.execute(
        select(DeviceLink).where(
            DeviceLink.parent_device_id == parent_device.id,
            DeviceLink.child_device_id == child_device.id
        )
    )
    if existing.scalars().first():
        raise HTTPException(400, "Device is already linked")

    # Create link
    link = DeviceLink(
        parent_device_id=parent_device.id,
        child_device_id=child_device.id,
        link_type=link_data.link_type,
        is_location_inherited=False  # Explicit link
    )

    session.add(link)
    await session.commit()
    await session.refresh(link)

    return DeviceLinkRead(
        id=link.id,
        link_type=link.link_type,
        is_location_inherited=link.is_location_inherited,
        created_at=link.created_at,
        child_device_id=child_device.device_id,
        child_device_name=child_device.name,
        child_device_system_name=child_device.system_name,
        child_device_type=child_device.device_type,
        child_device_is_online=child_device.is_online
    )


@router.delete("/{device_id}/links/{link_id}")
async def delete_device_link(
    device_id: str,
    link_id: int,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Remove a device link"""
    # Verify user owns the parent device
    result = await session.execute(
        select(Device).where(Device.device_id == device_id, Device.user_id == user.id)
    )
    parent_device = result.scalars().first()

    if not parent_device:
        raise HTTPException(404, "Device not found or not owned by you")

    # Find and delete the link
    link_result = await session.execute(
        select(DeviceLink).where(
            DeviceLink.id == link_id,
            DeviceLink.parent_device_id == parent_device.id
        )
    )
    link = link_result.scalars().first()

    if not link:
        raise HTTPException(404, "Link not found")

    await session.delete(link)
    await session.commit()

    return {"status": "success", "message": "Device link removed"}


# API Endpoints (for devices using API keys)

@api_router.post("/pair", response_model=DevicePairResponse)
async def pair_device(
    pair_request: DevicePairRequest,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Pair an environment sensor device to a user account.
    Device submits device_id, user approves via web UI, device polls for result.
    """
    # Check if device already exists
    result = await session.execute(select(Device).where(Device.device_id == pair_request.device_id))
    existing_device = result.scalars().first()

    if existing_device:
        # Device exists - check if it belongs to this user
        if existing_device.user_id == user.id:
            # Same user re-pairing their own device (e.g., after factory reset)
            # Generate new API key and update the existing device
            api_key = secrets.token_hex(32)
            existing_device.api_key = api_key
            existing_device.name = pair_request.device_name or existing_device.name
            existing_device.is_online = True
            existing_device.last_seen = datetime.utcnow()

            # Update location if provided
            if pair_request.location_id:
                existing_device.location_id = pair_request.location_id
            elif pair_request.location_name:
                new_location = Location(
                    name=pair_request.location_name,
                    user_id=user.id
                )
                session.add(new_location)
                await session.flush()
                existing_device.location_id = new_location.id

            await session.commit()
            await session.refresh(existing_device)

            # Store result for device to retrieve
            pairing_results[pair_request.device_id] = {
                "success": True,
                "api_key": api_key,
                "user_email": user.email,
                "message": "Device re-paired successfully (API key updated)"
            }

            return DevicePairResponse(
                success=True,
                api_key=api_key,
                device_id=pair_request.device_id,
                server_url="",
                message="Device re-paired successfully"
            )
        else:
            # Device belongs to another user
            raise HTTPException(400, "Device already paired to another account")

    # Generate API key for the device
    api_key = secrets.token_hex(32)

    # Handle location assignment
    location_id = pair_request.location_id
    if pair_request.location_name and not location_id:
        # Create new location if name provided but no ID
        new_location = Location(
            name=pair_request.location_name,
            user_id=user.id
        )
        session.add(new_location)
        await session.flush()
        location_id = new_location.id

    # Create new device
    new_device = Device(
        device_id=pair_request.device_id,
        api_key=api_key,
        name=pair_request.device_name or f"Sensor {pair_request.device_id[:8]}",
        device_type='environmental',
        scope='room',
        location_id=location_id,
        user_id=user.id,
        is_online=True,
        last_seen=datetime.utcnow()
    )

    session.add(new_device)
    await session.commit()
    await session.refresh(new_device)

    # Store result for device to retrieve
    pairing_results[pair_request.device_id] = {
        "success": True,
        "api_key": api_key,
        "user_email": user.email
    }

    return DevicePairResponse(
        success=True,
        api_key=api_key,
        device_id=pair_request.device_id,
        server_url="",  # Device already knows the server URL it's pairing to
        message="Device paired successfully"
    )


@api_router.get("/pair-status/{device_id}")
async def get_pair_status(device_id: str):
    """
    Device polls this endpoint to check if pairing was approved.
    Returns pairing result if available.
    """
    result = pairing_results.get(device_id)

    if result:
        # Clear result after retrieval
        del pairing_results[device_id]
        return result
    else:
        return {"success": False, "message": "Pairing not yet approved or not found"}


@api_router.options("/pair-status/{device_id}")
async def pair_status_options(device_id: str):
    """Handle CORS preflight for pair-status endpoint"""
    return {"message": "OK"}


@api_router.post("/{device_id}/unpair")
async def unpair_device(
    device_id: str,
    api_key: str = Query(...),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Device requests to unpair itself from the server.
    Deletes the device record using device_id and api_key for authentication.
    """
    # Verify device exists and API key matches
    result = await session.execute(
        select(Device).where(Device.device_id == device_id, Device.api_key == api_key)
    )
    device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found or invalid API key")

    # Delete the device
    await session.delete(device)
    await session.commit()

    return {"status": "success", "message": "Device unpaired successfully"}
