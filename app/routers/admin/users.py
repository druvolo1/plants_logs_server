# app/routers/admin/users.py
"""
User management endpoints for admin portal.
"""
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi_users import exceptions

from app.models import User, Device, Plant
from app.schemas import UserCreate, UserUpdate, PasswordReset
from app.routers.admin import get_current_admin_dependency, get_db_dependency, get_user_manager_dependency, get_templates

router = APIRouter()


# HTML Pages

@router.get("/overview", response_class=HTMLResponse)
async def admin_overview_page(
    request: Request,
    admin: User = Depends(get_current_admin_dependency())
):
    """Admin overview page (legacy)"""
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

    # Count pending users for sidebar badge
    pending_result = await session.execute(
        select(func.count(User.id)).where(User.is_active == False)
    )
    pending_count = pending_result.scalar() or 0

    return get_templates().TemplateResponse("users.html", {
        "request": request,
        "user": admin,
        "users": users,
        "active_page": "users",
        "pending_users_count": pending_count
    })


# API Endpoints

@router.get("/user-count")
async def get_user_count(
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get total user count"""
    result = await session.execute(select(func.count(User.id)))
    count = result.scalar()
    return {"count": count}


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


# User details API for admin
@router.get("/api/users/{user_id}")
async def get_user_details(
    user_id: int,
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get detailed user information"""
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    # Get device count
    device_result = await session.execute(
        select(func.count(Device.id)).where(Device.user_id == user_id)
    )
    device_count = device_result.scalar() or 0

    # Get plant count
    plant_result = await session.execute(
        select(func.count(Plant.id)).where(Plant.user_id == user_id)
    )
    plant_count = plant_result.scalar() or 0

    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_active": user.is_active,
        "is_suspended": getattr(user, "is_suspended", False),
        "is_superuser": user.is_superuser,
        "device_count": device_count,
        "plant_count": plant_count
    }


# Plant Management
@router.delete("/plants/{plant_id}", response_model=Dict[str, str])
async def delete_plant_admin(
    plant_id: str,
    user: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Delete a plant (admin only)"""
    result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id)
    )

    plant = result.scalars().first()
    if not plant:
        raise HTTPException(404, "Plant not found")

    await session.delete(plant)
    await session.commit()

    return {"status": "success", "message": f"Plant '{plant.name}' and all associated logs deleted successfully"}


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
