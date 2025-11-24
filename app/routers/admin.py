# app/routers/admin.py
"""
Admin endpoints for user management, overview, and system monitoring.
"""
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi_users import exceptions

from app.models import User, Device, Plant, DeviceAssignment
from app.schemas import UserCreate, UserUpdate, PasswordReset

router = APIRouter(prefix="/admin", tags=["admin"])


def get_current_admin_dependency():
    """Import and return current_admin dependency"""
    from app.main import current_admin
    return current_admin


def get_db_dependency():
    """Import and return get_db dependency"""
    from app.main import get_db
    return get_db


def get_user_manager_dependency():
    """Import and return get_user_manager dependency"""
    from app.main import get_user_manager
    return get_user_manager


def get_templates():
    """Import and return templates"""
    from app.main import templates
    return templates


# HTML Pages

@router.get("/overview", response_class=HTMLResponse)
async def admin_overview_page(
    request: Request,
    admin: User = Depends(get_current_admin_dependency())
):
    """Admin overview page"""
    return get_templates().TemplateResponse("admin_overview.html", {"request": request, "user": admin})


@router.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Users management page"""
    result = await session.execute(
        select(User).options(selectinload(User.oauth_accounts))
    )
    users = result.scalars().all()
    return get_templates().TemplateResponse("users.html", {"request": request, "user": admin, "users": users})


# API Endpoints

@router.get("/all-devices")
async def get_all_devices(
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get all devices in the system"""
    result = await session.execute(
        select(Device, User.email)
        .join(User, Device.user_id == User.id)
        .order_by(Device.id.desc())
    )

    devices_list = []
    for device, owner_email in result.all():
        # Check for active plant assignment
        assignment_result = await session.execute(
            select(DeviceAssignment, Plant)
            .join(Plant, DeviceAssignment.plant_id == Plant.id)
            .where(
                DeviceAssignment.device_id == device.id,
                DeviceAssignment.removed_at == None
            )
        )
        assignment_row = assignment_result.first()

        active_plant_name = None
        active_phase = None

        if assignment_row:
            assignment, plant = assignment_row
            active_plant_name = plant.name
            active_phase = assignment.phase

        devices_list.append({
            "device_id": device.device_id,
            "name": device.name,
            "owner_email": owner_email,
            "device_type": device.device_type,
            "is_online": device.is_online,
            "active_plant_name": active_plant_name,
            "active_phase": active_phase
        })

    return devices_list


@router.get("/all-plants")
async def get_all_plants(
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get all plants in the system"""
    result = await session.execute(
        select(Plant, User.email, Device.device_id)
        .join(User, Plant.user_id == User.id)
        .outerjoin(Device, Plant.device_id == Device.id)
        .order_by(Plant.id.desc())
    )

    plants_list = []
    for plant, owner_email, device_uuid in result.all():
        plants_list.append({
            "plant_id": plant.plant_id,
            "name": plant.name,
            "owner_email": owner_email,
            "device_id": device_uuid,
            "status": plant.status,
            "current_phase": plant.current_phase,
            "start_date": plant.start_date.isoformat() if plant.start_date else None,
            "end_date": plant.end_date.isoformat() if plant.end_date else None,
            "is_active": plant.end_date is None
        })

    return plants_list


@router.get("/user-count")
async def get_user_count(
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get total user count"""
    result = await session.execute(select(func.count(User.id)))
    count = result.scalar()
    return {"count": count}


# User Management

@router.post("/users")
async def add_user(
    user_data: UserCreate,
    admin: User = Depends(get_current_admin_dependency()),
    manager = Depends(get_user_manager_dependency())
):
    """Create a new user"""
    try:
        user = await manager.create(user_data)
        return {"status": "success", "user_id": user.id}
    except exceptions.UserAlreadyExists:
        raise HTTPException(400, "User already exists")


@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    admin: User = Depends(get_current_admin_dependency()),
    manager = Depends(get_user_manager_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Update user information"""
    user = await manager.user_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_dict = {}
    if user_data.email is not None:
        update_dict["email"] = user_data.email
    if user_data.first_name is not None:
        update_dict["first_name"] = user_data.first_name
    if user_data.last_name is not None:
        update_dict["last_name"] = user_data.last_name
    if user_data.is_active is not None:
        update_dict["is_active"] = user_data.is_active
    if user_data.is_superuser is not None:
        update_dict["is_superuser"] = user_data.is_superuser

    user = await manager.user_db.update(user, update_dict)
    return {"status": "success"}


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    password_reset: PasswordReset,
    admin: User = Depends(get_current_admin_dependency()),
    manager = Depends(get_user_manager_dependency())
):
    """Reset a user's password"""
    user = await manager.user_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    hashed_password = manager.password_helper.hash(password_reset.password)
    update_dict = {"hashed_password": hashed_password}
    user = await manager.user_db.update(user, update_dict)
    return {"status": "success"}


@router.post("/users/{user_id}/suspend")
async def suspend_user(
    user_id: int,
    admin: User = Depends(get_current_admin_dependency()),
    manager = Depends(get_user_manager_dependency())
):
    """Suspend a user"""
    user = await manager.user_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    update_dict = {"is_suspended": True}
    user = await manager.user_db.update(user, update_dict)
    return {"status": "success"}


@router.post("/users/{user_id}/unsuspend")
async def unsuspend_user(
    user_id: int,
    admin: User = Depends(get_current_admin_dependency()),
    manager = Depends(get_user_manager_dependency())
):
    """Unsuspend a user"""
    user = await manager.user_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    update_dict = {"is_suspended": False}
    user = await manager.user_db.update(user, update_dict)
    return {"status": "success"}


@router.post("/users/{user_id}/approve")
async def approve_user(
    user_id: int,
    admin: User = Depends(get_current_admin_dependency()),
    manager = Depends(get_user_manager_dependency())
):
    """Approve a pending user"""
    user = await manager.user_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    update_dict = {"is_active": True}
    user = await manager.user_db.update(user, update_dict)
    return {"status": "success"}


@router.delete("/users/{user_id}")
async def delete_user_admin(
    user_id: int,
    session: AsyncSession = Depends(get_db_dependency()),
    admin: User = Depends(get_current_admin_dependency())
):
    """Delete a user"""
    user = await session.get(User, user_id)
    if user:
        await session.delete(user)
        await session.commit()
        return {"status": "success"}
    raise HTTPException(404, "User not found")


# Plant Management

@router.delete("/plants/{plant_id}", response_model=Dict[str, str])
async def delete_plant_admin(
    plant_id: str,
    user: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Delete a plant (admin only)"""
    # Get plant
    result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id)
    )

    plant = result.scalars().first()
    if not plant:
        raise HTTPException(404, "Plant not found")

    # Delete plant (logs will be cascade deleted)
    await session.delete(plant)
    await session.commit()

    return {"status": "success", "message": f"Plant '{plant.name}' and all associated logs deleted successfully"}
