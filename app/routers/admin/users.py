# app/routers/admin/users.py
"""
User management endpoints for admin portal.
"""
from typing import Dict, List
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi_users import exceptions

from app.models import User, Device, Plant
from app.schemas import UserCreate, UserUpdate, PasswordReset

router = APIRouter()

# In-memory impersonation store (in production, use Redis or session store)
# Format: {admin_user_id: impersonated_user_id}
impersonation_sessions = {}


def _get_current_admin():
    from app.main import current_admin
    return current_admin


def _get_db():
    from app.main import get_db
    return get_db


def _get_user_manager():
    from app.main import get_user_manager
    return get_user_manager


def _get_templates():
    from app.main import templates
    return templates


# HTML Pages

@router.get("/overview", response_class=HTMLResponse)
async def admin_overview_page(
    request: Request,
    admin: User = Depends(_get_current_admin())
):
    """Admin overview page (legacy)"""
    return _get_templates().TemplateResponse("admin_overview.html", {"request": request, "user": admin})


@router.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
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

    return _get_templates().TemplateResponse("admin_users.html", {
        "request": request,
        "user": admin,
        "users": users,
        "active_page": "users",
        "pending_users_count": pending_count
    })


# API Endpoints

@router.get("/user-count")
async def get_user_count(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Get total user count"""
    result = await session.execute(select(func.count(User.id)))
    count = result.scalar()
    return {"count": count}


@router.post("/users")
async def add_user(
    user_data: UserCreate,
    admin: User = Depends(_get_current_admin()),
    manager = Depends(_get_user_manager())
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
    admin: User = Depends(_get_current_admin()),
    manager = Depends(_get_user_manager()),
    session: AsyncSession = Depends(_get_db())
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
    admin: User = Depends(_get_current_admin()),
    manager = Depends(_get_user_manager())
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
    admin: User = Depends(_get_current_admin()),
    manager = Depends(_get_user_manager())
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
    admin: User = Depends(_get_current_admin()),
    manager = Depends(_get_user_manager())
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
    admin: User = Depends(_get_current_admin()),
    manager = Depends(_get_user_manager())
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
    session: AsyncSession = Depends(_get_db()),
    admin: User = Depends(_get_current_admin())
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
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
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
    user: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
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
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
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


# User counts API for the admin users table
@router.get("/api/users/counts")
async def get_users_counts(
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Get device and plant counts for all users"""
    # Get all users with their device and plant counts
    users_result = await session.execute(select(User))
    users = users_result.scalars().all()

    counts = []
    for user in users:
        device_result = await session.execute(
            select(func.count(Device.id)).where(Device.user_id == user.id)
        )
        plant_result = await session.execute(
            select(func.count(Plant.id)).where(Plant.user_id == user.id)
        )

        counts.append({
            "id": user.id,
            "device_count": device_result.scalar() or 0,
            "plant_count": plant_result.scalar() or 0
        })

    return counts


# Impersonation Endpoints

@router.post("/impersonate/{user_id}")
async def start_impersonation(
    user_id: int,
    request: Request,
    response: Response,
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Start impersonating a user - admin can view as this user"""
    # Verify target user exists
    target_user = await session.get(User, user_id)
    if not target_user:
        raise HTTPException(404, "User not found")

    # Don't allow impersonating yourself
    if target_user.id == admin.id:
        raise HTTPException(400, "Cannot impersonate yourself")

    # Store impersonation session
    impersonation_sessions[admin.id] = user_id

    # Set a cookie to track impersonation across requests
    response.set_cookie(
        key="impersonate_user_id",
        value=str(user_id),
        httponly=True,
        max_age=3600,  # 1 hour max
        samesite="lax"
    )

    print(f"[ADMIN] {admin.email} started impersonating user {target_user.email}")

    return {"status": "success", "impersonating": target_user.email}


@router.post("/impersonate/exit")
async def exit_impersonation(
    request: Request,
    response: Response,
    admin: User = Depends(_get_current_admin())
):
    """Exit impersonation mode"""
    # Remove from in-memory store
    if admin.id in impersonation_sessions:
        del impersonation_sessions[admin.id]

    # Clear cookie
    response.delete_cookie("impersonate_user_id")

    print(f"[ADMIN] {admin.email} exited impersonation mode")

    return {"status": "success"}


@router.get("/impersonate/status")
async def get_impersonation_status(
    request: Request,
    admin: User = Depends(_get_current_admin()),
    session: AsyncSession = Depends(_get_db())
):
    """Check if currently impersonating a user"""
    impersonated_id = request.cookies.get("impersonate_user_id")

    if impersonated_id:
        try:
            user_id = int(impersonated_id)
            user = await session.get(User, user_id)
            if user:
                return {
                    "impersonating": True,
                    "user_id": user.id,
                    "email": user.email,
                    "name": f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email
                }
        except (ValueError, TypeError):
            pass

    return {"impersonating": False}


def get_impersonated_user_id(request: Request) -> int | None:
    """Helper to get impersonated user ID from cookie"""
    impersonated_id = request.cookies.get("impersonate_user_id")
    if impersonated_id:
        try:
            return int(impersonated_id)
        except (ValueError, TypeError):
            pass
    return None
