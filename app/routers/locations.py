# app/routers/locations.py
"""
Location management endpoints including CRUD and sharing.
"""
from typing import List, Dict
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.models import User, Location, LocationShare
from app.schemas import (
    LocationCreate,
    LocationUpdate,
    LocationRead,
    LocationShareCreate,
    LocationShareRead,
    ShareAccept,
    ShareUpdate,
)

router = APIRouter(prefix="/user/locations", tags=["locations"])


def get_current_user_dependency():
    """Import and return current_user dependency"""
    from app.main import current_user
    return current_user


def get_db_dependency():
    """Import and return get_db dependency"""
    from app.main import get_db
    return get_db


async def generate_share_code(session: AsyncSession) -> str:
    """Generate a unique 10-character alphanumeric share code."""
    import string
    import random
    from app.models import DeviceShare

    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.ascii_lowercase + string.digits, k=10))
        # Check if code already exists in both tables
        device_result = await session.execute(select(DeviceShare).where(DeviceShare.share_code == code))
        location_result = await session.execute(select(LocationShare).where(LocationShare.share_code == code))
        if not device_result.scalars().first() and not location_result.scalars().first():
            return code


# CRUD Endpoints

@router.post("", response_model=LocationRead)
async def create_location(
    location: LocationCreate,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Create a new location"""
    # Verify parent exists if parent_id is provided
    if location.parent_id:
        parent_result = await session.execute(select(Location).where(Location.id == location.parent_id, Location.user_id == user.id))
        parent = parent_result.scalars().first()
        if not parent:
            raise HTTPException(404, "Parent location not found")

    new_location = Location(
        name=location.name,
        description=location.description,
        parent_id=location.parent_id,
        user_id=user.id
    )
    session.add(new_location)
    await session.commit()
    await session.refresh(new_location)

    return LocationRead(
        id=new_location.id,
        name=new_location.name,
        description=new_location.description,
        parent_id=new_location.parent_id,
        user_id=new_location.user_id,
        created_at=new_location.created_at,
        updated_at=new_location.updated_at,
        is_owner=True
    )


@router.get("", response_model=List[LocationRead])
async def list_locations(
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """List all locations owned by or shared with the user"""
    locations_list = []

    # Get owned locations
    owned_result = await session.execute(select(Location).where(Location.user_id == user.id))
    for location in owned_result.scalars().all():
        locations_list.append(LocationRead(
            id=location.id,
            name=location.name,
            description=location.description,
            parent_id=location.parent_id,
            user_id=location.user_id,
            created_at=location.created_at,
            updated_at=location.updated_at,
            is_owner=True
        ))

    # Get shared locations (accepted and active)
    shared_result = await session.execute(
        select(LocationShare)
        .where(
            LocationShare.shared_with_user_id == user.id,
            LocationShare.is_active == True,
            LocationShare.accepted_at != None,
            LocationShare.revoked_at == None,
            or_(LocationShare.expires_at == None, LocationShare.expires_at > datetime.utcnow())
        )
    )

    for share in shared_result.scalars().all():
        location_result = await session.execute(select(Location).where(Location.id == share.location_id))
        location = location_result.scalars().first()
        if location:
            owner_result = await session.execute(select(User).where(User.id == share.owner_user_id))
            owner = owner_result.scalars().first()
            owner_email = owner.email if owner else "Unknown"

            locations_list.append(LocationRead(
                id=location.id,
                name=location.name,
                description=location.description,
                parent_id=location.parent_id,
                user_id=location.user_id,
                created_at=location.created_at,
                updated_at=location.updated_at,
                is_owner=False,
                permission_level=share.permission_level,
                shared_by_email=owner_email
            ))

    return locations_list


@router.get("/{location_id}", response_model=LocationRead)
async def get_location(
    location_id: int,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get a specific location by ID"""
    result = await session.execute(select(Location).where(Location.id == location_id))
    location = result.scalars().first()

    if not location:
        raise HTTPException(404, "Location not found")

    # Check if user owns or has access to this location
    if location.user_id != user.id:
        # Check if location is shared with user
        share_result = await session.execute(
            select(LocationShare).where(
                LocationShare.location_id == location_id,
                LocationShare.shared_with_user_id == user.id,
                LocationShare.is_active == True,
                LocationShare.accepted_at != None,
                LocationShare.revoked_at == None,
                or_(LocationShare.expires_at == None, LocationShare.expires_at > datetime.utcnow())
            )
        )
        share = share_result.scalars().first()
        if not share:
            raise HTTPException(403, "Access denied")

        owner_result = await session.execute(select(User).where(User.id == location.user_id))
        owner = owner_result.scalars().first()

        return LocationRead(
            id=location.id,
            name=location.name,
            description=location.description,
            parent_id=location.parent_id,
            user_id=location.user_id,
            created_at=location.created_at,
            updated_at=location.updated_at,
            is_owner=False,
            permission_level=share.permission_level,
            shared_by_email=owner.email if owner else "Unknown"
        )

    return LocationRead(
        id=location.id,
        name=location.name,
        description=location.description,
        parent_id=location.parent_id,
        user_id=location.user_id,
        created_at=location.created_at,
        updated_at=location.updated_at,
        is_owner=True
    )


@router.put("/{location_id}", response_model=LocationRead)
async def update_location(
    location_id: int,
    location_update: LocationUpdate,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Update a location"""
    result = await session.execute(select(Location).where(Location.id == location_id, Location.user_id == user.id))
    location = result.scalars().first()

    if not location:
        raise HTTPException(404, "Location not found or access denied")

    # Verify parent exists if parent_id is being updated
    if location_update.parent_id is not None:
        if location_update.parent_id == location_id:
            raise HTTPException(400, "Location cannot be its own parent")
        parent_result = await session.execute(select(Location).where(Location.id == location_update.parent_id, Location.user_id == user.id))
        parent = parent_result.scalars().first()
        if not parent:
            raise HTTPException(404, "Parent location not found")

    # Update fields
    if location_update.name is not None:
        location.name = location_update.name
    if location_update.description is not None:
        location.description = location_update.description
    if location_update.parent_id is not None:
        location.parent_id = location_update.parent_id

    await session.commit()
    await session.refresh(location)

    return LocationRead(
        id=location.id,
        name=location.name,
        description=location.description,
        parent_id=location.parent_id,
        user_id=location.user_id,
        created_at=location.created_at,
        updated_at=location.updated_at,
        is_owner=True
    )


@router.delete("/{location_id}")
async def delete_location(
    location_id: int,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Delete a location"""
    result = await session.execute(select(Location).where(Location.id == location_id, Location.user_id == user.id))
    location = result.scalars().first()

    if not location:
        raise HTTPException(404, "Location not found or access denied")

    await session.delete(location)
    await session.commit()

    return {"status": "success", "message": "Location deleted"}


# Sharing Endpoints

@router.post("/{location_id}/share", response_model=Dict[str, str])
async def create_location_share(
    location_id: int,
    share_data: LocationShareCreate,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Create a share code for a location"""
    # Verify user owns the location
    result = await session.execute(select(Location).where(Location.id == location_id, Location.user_id == user.id))
    location = result.scalars().first()
    if not location:
        raise HTTPException(404, "Location not found or not owned by you")

    # Validate permission level
    if share_data.permission_level not in ['viewer', 'controller']:
        raise HTTPException(400, "Invalid permission level. Must be 'viewer' or 'controller'")

    # Generate unique share code
    share_code = await generate_share_code(session)

    # Create share with expiration (None for never expire)
    expires_at = None if share_data.expires_in_days is None else datetime.utcnow() + timedelta(days=share_data.expires_in_days)

    share = LocationShare(
        location_id=location.id,
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
async def accept_location_share(
    share_data: ShareAccept,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Accept a location share using a share code"""
    # Find the share by code
    result = await session.execute(
        select(LocationShare).where(
            LocationShare.share_code == share_data.share_code,
            LocationShare.is_active == True,
            LocationShare.accepted_at == None
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

    # Get location info
    location_result = await session.execute(select(Location).where(Location.id == share.location_id))
    location = location_result.scalars().first()

    return {"status": "success", "location_id": str(location.id) if location else "unknown", "location_name": location.name if location else "unknown"}


@router.get("/{location_id}/shares", response_model=List[LocationShareRead])
async def list_location_shares(
    location_id: int,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """List all shares for a location (owner only)"""
    # Verify ownership
    location_result = await session.execute(select(Location).where(Location.id == location_id, Location.user_id == user.id))
    location = location_result.scalars().first()
    if not location:
        raise HTTPException(404, "Location not found or not owned by you")

    # Get all active shares
    shares_result = await session.execute(
        select(LocationShare).where(
            LocationShare.location_id == location.id,
            LocationShare.owner_user_id == user.id,
            LocationShare.revoked_at == None
        )
    )

    shares_list = []
    for share in shares_result.scalars().all():
        shared_with_email = None
        if share.shared_with_user_id:
            user_result = await session.execute(select(User).where(User.id == share.shared_with_user_id))
            shared_user = user_result.scalars().first()
            shared_with_email = shared_user.email if shared_user else None

        shares_list.append(LocationShareRead(
            id=share.id,
            location_id=share.location_id,
            share_code=share.share_code,
            permission_level=share.permission_level,
            created_at=share.created_at,
            expires_at=share.expires_at,
            accepted_at=share.accepted_at,
            is_active=share.is_active,
            shared_with_email=shared_with_email
        ))

    return shares_list


@router.delete("/{location_id}/shares/{share_id}")
async def revoke_location_share(
    location_id: int,
    share_id: int,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Revoke a location share"""
    # Verify ownership and get share
    share_result = await session.execute(
        select(LocationShare).where(
            LocationShare.id == share_id,
            LocationShare.location_id == location_id,
            LocationShare.owner_user_id == user.id
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


@router.put("/{location_id}/shares/{share_id}/permission")
async def update_location_share_permission(
    location_id: int,
    share_id: int,
    share_data: ShareUpdate,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Update the permission level of a location share"""
    # Validate permission level
    if share_data.permission_level not in ['viewer', 'controller']:
        raise HTTPException(400, "Invalid permission level. Must be 'viewer' or 'controller'")

    # Find the share and verify ownership
    result = await session.execute(
        select(LocationShare).where(
            LocationShare.id == share_id,
            LocationShare.location_id == location_id,
            LocationShare.owner_user_id == user.id
        )
    )
    share = result.scalars().first()

    if not share:
        raise HTTPException(404, "Share not found or not owned by you")

    # Update permission
    share.permission_level = share_data.permission_level

    await session.commit()

    return {"status": "success", "permission_level": share.permission_level}
