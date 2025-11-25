# app/routers/plants.py
"""
Plant management endpoints including CRUD, device assignments, and phase management.
"""
from typing import List, Dict
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.models import User, Device, Plant, DeviceAssignment, PhaseHistory, PhaseTemplate, DeviceShare
from app.schemas import (
    PlantCreate,
    PlantCreateNew,
    PlantRead,
    PlantAssignmentRead,
    PhaseHistoryRead,
)

router = APIRouter(prefix="/user/plants", tags=["plants"])
api_router = APIRouter(prefix="/api/devices", tags=["plants-api"])


def get_current_user_dependency():
    """Import and return current_user dependency"""
    from app.main import current_user
    return current_user


def get_db_dependency():
    """Import and return get_db dependency"""
    from app.main import get_db
    return get_db


# Plant CRUD Endpoints

@router.post("", response_model=Dict[str, str])
async def create_plant(
    plant_data: PlantCreate,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Create a plant with device assignment (legacy endpoint)"""
    # Verify device exists and user has access (owns or has controller permission)
    result = await session.execute(select(Device).where(Device.device_id == plant_data.device_id))
    device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    # Only feeding_system devices can have plants assigned
    if device.device_type != 'feeding_system':
        device_type_name = {
            'environmental': 'environmental sensor',
            'valve_controller': 'valve controller',
            'other': 'this device type'
        }.get(device.device_type, device.device_type)
        raise HTTPException(400, f"Cannot assign plants to {device_type_name}. Only feeding systems can have plants assigned.")

    # Check if user owns device
    is_owner = device.user_id == user.id

    # If not owner, check if user has controller permission
    if not is_owner:
        result = await session.execute(
            select(DeviceShare).where(
                DeviceShare.device_id == device.id,
                DeviceShare.shared_with_user_id == user.id,
                DeviceShare.is_active == True,
                DeviceShare.revoked_at == None,
                DeviceShare.accepted_at != None,
                DeviceShare.permission_level == 'controller'
            )
        )
        share = result.scalars().first()

        if not share:
            raise HTTPException(403, "You don't have permission to create plants on this device")

    # Generate unique plant_id using timestamp
    plant_id = str(int(datetime.utcnow().timestamp() * 1000000))  # Microsecond precision

    # Create plant
    new_plant = Plant(
        plant_id=plant_id,
        name=plant_data.name,
        system_id=plant_data.system_id,
        device_id=device.id,
        user_id=device.user_id,  # Plant belongs to device owner
        location_id=plant_data.location_id,
        start_date=datetime.utcnow()
    )

    session.add(new_plant)
    await session.commit()
    await session.refresh(new_plant)

    return {"plant_id": plant_id, "message": "Plant started successfully"}


@router.post("/new", response_model=Dict[str, str])
async def create_plant_new(
    plant_data: PlantCreateNew,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Create a plant without device assignment - server-side creation"""
    # Verify location if provided
    if plant_data.location_id:
        from app.models import Location
        location_result = await session.execute(select(Location).where(Location.id == plant_data.location_id, Location.user_id == user.id))
        location = location_result.scalars().first()
        if not location:
            raise HTTPException(404, "Location not found or access denied")

    # Generate unique plant_id using timestamp
    plant_id = str(int(datetime.utcnow().timestamp() * 1000000))  # Microsecond precision

    # Get template if provided
    template = None
    if plant_data.template_id:
        template_result = await session.execute(
            select(PhaseTemplate).where(
                PhaseTemplate.id == plant_data.template_id,
                PhaseTemplate.user_id == user.id
            )
        )
        template = template_result.scalars().first()
        if not template:
            raise HTTPException(404, "Template not found")

    # Create plant
    new_plant = Plant(
        plant_id=plant_id,
        name=plant_data.name,
        batch_number=plant_data.batch_number,
        user_id=user.id,
        location_id=plant_data.location_id,
        start_date=datetime.utcnow(),
        status='created',
        current_phase=plant_data.starting_phase or 'seed',
        template_id=plant_data.template_id,
        expected_seed_days=template.expected_seed_days if template else None,
        expected_clone_days=template.expected_clone_days if template else None,
        expected_veg_days=template.expected_veg_days if template else None,
        expected_flower_days=template.expected_flower_days if template else None,
        expected_drying_days=template.expected_drying_days if template else None,
        expected_curing_days=template.expected_curing_days if template else None,
    )

    session.add(new_plant)
    await session.commit()
    await session.refresh(new_plant)

    # Create initial phase history entry
    phase_history = PhaseHistory(
        plant_id=new_plant.id,
        phase=new_plant.current_phase,
        started_at=datetime.utcnow()
    )
    session.add(phase_history)
    await session.commit()

    return {"plant_id": plant_id, "message": f"Plant '{new_plant.name}' created successfully"}


@router.get("", response_model=List[PlantRead])
async def list_plants(
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """List all plants owned by or shared with the user"""
    # Get plants owned by user or where user has access through device sharing
    result = await session.execute(
        select(Plant, Device)
        .outerjoin(Device, Plant.device_id == Device.id)
        .where(
            or_(Plant.user_id == user.id, Device.user_id == user.id)
        )
        .order_by(Plant.display_order.asc(), Plant.id.desc())
    )

    plants_list = []
    for plant, device in result.all():
        # Get active device assignment if any
        assignment_result = await session.execute(
            select(DeviceAssignment, Device)
            .join(Device, DeviceAssignment.device_id == Device.id)
            .where(
                DeviceAssignment.plant_id == plant.id,
                DeviceAssignment.removed_at == None
            )
        )
        assignment_row = assignment_result.first()

        device_name = None
        device_id = None
        if assignment_row:
            assignment, assigned_device = assignment_row
            device_name = assigned_device.name
            device_id = assigned_device.device_id

        plants_list.append(PlantRead(
            id=plant.id,
            plant_id=plant.plant_id,
            name=plant.name,
            batch_number=plant.batch_number,
            system_id=plant.system_id,
            device_id=device_id,
            device_name=device_name,
            location_id=plant.location_id,
            start_date=plant.start_date,
            end_date=plant.end_date,
            yield_grams=plant.yield_grams,
            status=plant.status,
            current_phase=plant.current_phase,
            harvest_date=plant.harvest_date,
            cure_start_date=plant.cure_start_date,
            cure_end_date=plant.cure_end_date,
            expected_seed_days=plant.expected_seed_days,
            expected_clone_days=plant.expected_clone_days,
            expected_veg_days=plant.expected_veg_days,
            expected_flower_days=plant.expected_flower_days,
            expected_drying_days=plant.expected_drying_days,
            expected_curing_days=plant.expected_curing_days,
            template_id=plant.template_id
        ))

    return plants_list


@router.get("/{plant_id}", response_model=PlantRead)
async def get_plant(
    plant_id: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get a specific plant by ID"""
    result = await session.execute(
        select(Plant, Device)
        .outerjoin(Device, Plant.device_id == Device.id)
        .where(
            Plant.plant_id == plant_id,
            or_(Plant.user_id == user.id, Device.user_id == user.id)
        )
    )

    row = result.first()
    if not row:
        raise HTTPException(404, "Plant not found")

    plant, device = row

    # Get active device assignment if any
    assignment_result = await session.execute(
        select(DeviceAssignment, Device)
        .join(Device, DeviceAssignment.device_id == Device.id)
        .where(
            DeviceAssignment.plant_id == plant.id,
            DeviceAssignment.removed_at == None
        )
    )
    assignment_row = assignment_result.first()

    device_name = None
    device_id = None
    if assignment_row:
        assignment, assigned_device = assignment_row
        device_name = assigned_device.name
        device_id = assigned_device.device_id

    return PlantRead(
        id=plant.id,
        plant_id=plant.plant_id,
        name=plant.name,
        batch_number=plant.batch_number,
        system_id=plant.system_id,
        device_id=device_id,
        device_name=device_name,
        location_id=plant.location_id,
        start_date=plant.start_date,
        end_date=plant.end_date,
        yield_grams=plant.yield_grams,
        status=plant.status,
        current_phase=plant.current_phase,
        harvest_date=plant.harvest_date,
        cure_start_date=plant.cure_start_date,
        cure_end_date=plant.cure_end_date,
        expected_seed_days=plant.expected_seed_days,
        expected_clone_days=plant.expected_clone_days,
        expected_veg_days=plant.expected_veg_days,
        expected_flower_days=plant.expected_flower_days,
        expected_drying_days=plant.expected_drying_days,
        expected_curing_days=plant.expected_curing_days,
        template_id=plant.template_id
    )


@router.delete("/{plant_id}", response_model=Dict[str, str])
async def delete_plant(
    plant_id: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Delete a plant"""
    # Get plant
    result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id, Plant.user_id == user.id)
    )

    plant = result.scalars().first()
    if not plant:
        raise HTTPException(404, "Plant not found")

    # Delete plant (logs will be cascade deleted)
    await session.delete(plant)
    await session.commit()

    return {"status": "success", "message": f"Plant '{plant.name}' and all associated logs deleted successfully"}


# Device Assignment Endpoints

@router.get("/{plant_id}/assignments")
async def get_plant_assignments(
    plant_id: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get all device assignments for a plant"""
    # Verify plant exists and user has access
    result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id, Plant.user_id == user.id)
    )
    plant = result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found")

    # Get all assignments (current and historical)
    assignments_result = await session.execute(
        select(DeviceAssignment, Device)
        .join(Device, DeviceAssignment.device_id == Device.id)
        .where(DeviceAssignment.plant_id == plant.id)
        .order_by(DeviceAssignment.assigned_at.desc())
    )

    assignments_list = []
    for assignment, device in assignments_result.all():
        assignments_list.append(PlantAssignmentRead(
            id=assignment.id,
            plant_id=plant.plant_id,
            device_id=device.device_id,
            device_name=device.name,
            assigned_at=assignment.assigned_at,
            removed_at=assignment.removed_at,
            is_active=assignment.removed_at is None
        ))

    return assignments_list


@router.post("/{plant_id}/assign", response_model=Dict[str, str])
async def assign_device_to_plant(
    plant_id: str,
    device_id: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Assign a device to a plant"""
    # Verify plant exists and user has access
    result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id, Plant.user_id == user.id)
    )
    plant = result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found")

    # Verify device exists and user has access
    device_result = await session.execute(select(Device).where(Device.device_id == device_id))
    device = device_result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    # Only feeding_system devices can have plants assigned
    if device.device_type != 'feeding_system':
        device_type_name = {
            'environmental': 'environmental sensor',
            'valve_controller': 'valve controller',
            'other': 'this device type'
        }.get(device.device_type, device.device_type)
        raise HTTPException(400, f"Cannot assign plants to {device_type_name}. Only feeding systems can have plants assigned.")

    # Check if user owns device or has controller permission
    is_owner = device.user_id == user.id

    if not is_owner:
        share_result = await session.execute(
            select(DeviceShare).where(
                DeviceShare.device_id == device.id,
                DeviceShare.shared_with_user_id == user.id,
                DeviceShare.is_active == True,
                DeviceShare.revoked_at == None,
                DeviceShare.accepted_at != None,
                DeviceShare.permission_level == 'controller'
            )
        )
        share = share_result.scalars().first()

        if not share:
            raise HTTPException(403, "You don't have permission to use this device")

    # Check if plant already has an active assignment
    existing_result = await session.execute(
        select(DeviceAssignment).where(
            DeviceAssignment.plant_id == plant.id,
            DeviceAssignment.removed_at == None
        )
    )
    existing_assignment = existing_result.scalars().first()

    if existing_assignment:
        raise HTTPException(400, "Plant already has an active device assignment. Unassign first.")

    # Create new assignment
    assignment = DeviceAssignment(
        plant_id=plant.id,
        device_id=device.id,
        assigned_at=datetime.utcnow()
    )

    session.add(assignment)
    await session.commit()

    return {"status": "success", "message": f"Device '{device.name}' assigned to plant '{plant.name}'"}


@router.post("/{plant_id}/unassign", response_model=Dict[str, str])
async def unassign_device_from_plant(
    plant_id: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Unassign the current device from a plant"""
    # Verify plant exists and user has access
    result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id, Plant.user_id == user.id)
    )
    plant = result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found")

    # Find active assignment
    assignment_result = await session.execute(
        select(DeviceAssignment).where(
            DeviceAssignment.plant_id == plant.id,
            DeviceAssignment.removed_at == None
        )
    )
    assignment = assignment_result.scalars().first()

    if not assignment:
        raise HTTPException(404, "No active device assignment found")

    # Mark assignment as removed
    assignment.removed_at = datetime.utcnow()
    await session.commit()

    return {"status": "success", "message": "Device unassigned from plant"}


# Phase Management Endpoints

@router.post("/{plant_id}/change-phase", response_model=Dict[str, str])
async def change_plant_phase(
    plant_id: str,
    new_phase: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Change the current phase of a plant"""
    # Verify plant exists and user has access
    result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id, Plant.user_id == user.id)
    )
    plant = result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found")

    # Valid phases
    valid_phases = ['seed', 'clone', 'veg', 'flower', 'drying', 'curing']
    if new_phase not in valid_phases:
        raise HTTPException(400, f"Invalid phase. Must be one of: {', '.join(valid_phases)}")

    old_phase = plant.current_phase

    # Update plant phase
    plant.current_phase = new_phase

    # End the current phase in history
    if old_phase:
        current_phase_result = await session.execute(
            select(PhaseHistory).where(
                PhaseHistory.plant_id == plant.id,
                PhaseHistory.phase == old_phase,
                PhaseHistory.ended_at == None
            )
        )
        current_phase_history = current_phase_result.scalars().first()

        if current_phase_history:
            current_phase_history.ended_at = datetime.utcnow()

    # Create new phase history entry
    new_phase_history = PhaseHistory(
        plant_id=plant.id,
        phase=new_phase,
        started_at=datetime.utcnow()
    )
    session.add(new_phase_history)

    # Update status based on phase
    if new_phase in ['seed', 'clone', 'veg', 'flower']:
        plant.status = 'feeding'
    elif new_phase == 'drying':
        plant.status = 'harvested'
        if not plant.harvest_date:
            plant.harvest_date = datetime.utcnow()
    elif new_phase == 'curing':
        plant.status = 'curing'
        if not plant.cure_start_date:
            plant.cure_start_date = datetime.utcnow()

    await session.commit()

    return {"status": "success", "message": f"Plant phase changed from '{old_phase}' to '{new_phase}'"}


@router.get("/{plant_id}/phase-history")
async def get_phase_history(
    plant_id: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get phase history for a plant"""
    # Verify plant exists and user has access
    result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id, Plant.user_id == user.id)
    )
    plant = result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found")

    # Get phase history
    history_result = await session.execute(
        select(PhaseHistory)
        .where(PhaseHistory.plant_id == plant.id)
        .order_by(PhaseHistory.started_at.asc())
    )

    history_list = []
    for history in history_result.scalars().all():
        history_list.append(PhaseHistoryRead(
            id=history.id,
            plant_id=plant.plant_id,
            phase=history.phase,
            started_at=history.started_at,
            ended_at=history.ended_at,
            duration_days=(history.ended_at - history.started_at).days if history.ended_at else None
        ))

    return history_list


# Plant Finish/Completion Endpoints

@router.post("/{plant_id}/finish", response_model=Dict[str, str])
async def finish_plant(
    plant_id: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Mark a plant as finished"""
    # Verify plant exists and user has access
    result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id, Plant.user_id == user.id)
    )
    plant = result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found")

    # Mark plant as finished
    plant.end_date = datetime.utcnow()
    plant.status = 'finished'

    if plant.current_phase == 'curing' and not plant.cure_end_date:
        plant.cure_end_date = datetime.utcnow()

    # End any active phase in history
    active_phase_result = await session.execute(
        select(PhaseHistory).where(
            PhaseHistory.plant_id == plant.id,
            PhaseHistory.ended_at == None
        )
    )
    active_phase = active_phase_result.scalars().first()

    if active_phase:
        active_phase.ended_at = datetime.utcnow()

    # Unassign any active device
    assignment_result = await session.execute(
        select(DeviceAssignment).where(
            DeviceAssignment.plant_id == plant.id,
            DeviceAssignment.removed_at == None
        )
    )
    assignment = assignment_result.scalars().first()

    if assignment:
        assignment.removed_at = datetime.utcnow()

    await session.commit()

    return {"status": "success", "message": f"Plant '{plant.name}' marked as finished"}


# Plant Update Endpoints

@router.patch("/{plant_id}/name", response_model=Dict[str, str])
async def update_plant_name(
    plant_id: str,
    name: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Update plant name"""
    result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id, Plant.user_id == user.id)
    )
    plant = result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found")

    plant.name = name
    await session.commit()

    return {"status": "success", "message": "Plant name updated"}


@router.patch("/{plant_id}/batch", response_model=Dict[str, str])
async def update_plant_batch(
    plant_id: str,
    batch_number: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Update plant batch number"""
    result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id, Plant.user_id == user.id)
    )
    plant = result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found")

    plant.batch_number = batch_number
    await session.commit()

    return {"status": "success", "message": "Batch number updated"}


@router.patch("/{plant_id}/apply-template", response_model=Dict[str, str])
async def apply_template_to_plant(
    plant_id: str,
    template_id: int,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Apply a phase template to a plant"""
    # Verify plant exists and user has access
    result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id, Plant.user_id == user.id)
    )
    plant = result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found")

    # Verify template exists and user has access
    template_result = await session.execute(
        select(PhaseTemplate).where(
            PhaseTemplate.id == template_id,
            PhaseTemplate.user_id == user.id
        )
    )
    template = template_result.scalars().first()

    if not template:
        raise HTTPException(404, "Template not found")

    # Apply template to plant
    plant.template_id = template.id
    plant.expected_seed_days = template.expected_seed_days
    plant.expected_clone_days = template.expected_clone_days
    plant.expected_veg_days = template.expected_veg_days
    plant.expected_flower_days = template.expected_flower_days
    plant.expected_drying_days = template.expected_drying_days
    plant.expected_curing_days = template.expected_curing_days

    await session.commit()

    return {"status": "success", "message": f"Template '{template.name}' applied to plant"}


@router.patch("/{plant_id}/yield", response_model=Dict[str, str])
async def update_plant_yield(
    plant_id: str,
    yield_grams: float,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Update plant yield"""
    result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id, Plant.user_id == user.id)
    )
    plant = result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found")

    plant.yield_grams = yield_grams
    await session.commit()

    return {"status": "success", "message": "Yield updated"}


@router.put("/reorder")
async def reorder_plants(
    plant_order: List[str],
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Reorder plants for display"""
    # Update display_order for each plant
    for index, plant_id in enumerate(plant_order):
        result = await session.execute(
            select(Plant).where(Plant.plant_id == plant_id, Plant.user_id == user.id)
        )
        plant = result.scalars().first()

        if plant:
            plant.display_order = index

    await session.commit()

    return {"status": "success", "message": "Plants reordered"}


# API Endpoints (for devices using API keys)

@api_router.post("/{device_id}/plants", response_model=Dict[str, str])
async def create_plant_device(
    device_id: str,
    plant_data: PlantCreate,
    api_key: str = Query(...),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Create a plant from a device using API key"""
    # Verify device and API key
    result = await session.execute(select(Device).where(Device.device_id == device_id, Device.api_key == api_key))
    device = result.scalars().first()

    if not device:
        raise HTTPException(401, "Invalid device or API key")

    # Only feeding_system devices can have plants assigned
    if device.device_type != 'feeding_system':
        raise HTTPException(400, "Only feeding systems can have plants assigned")

    # Generate unique plant_id using timestamp
    plant_id = str(int(datetime.utcnow().timestamp() * 1000000))  # Microsecond precision

    # Create plant
    new_plant = Plant(
        plant_id=plant_id,
        name=plant_data.name,
        system_id=plant_data.system_id,
        device_id=device.id,
        user_id=device.user_id,  # Plant belongs to device owner
        location_id=plant_data.location_id,
        start_date=datetime.utcnow()
    )

    session.add(new_plant)
    await session.commit()
    await session.refresh(new_plant)

    return {"plant_id": plant_id, "message": "Plant started successfully"}


@api_router.post("/{device_id}/plants/{plant_id}/finish", response_model=Dict[str, str])
async def finish_plant_device(
    device_id: str,
    plant_id: str,
    api_key: str = Query(...),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Finish a plant from a device using API key"""
    # Verify device and API key
    result = await session.execute(select(Device).where(Device.device_id == device_id, Device.api_key == api_key))
    device = result.scalars().first()

    if not device:
        raise HTTPException(401, "Invalid device or API key")

    # Get plant and verify it belongs to this device
    plant_result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id, Plant.device_id == device.id)
    )
    plant = plant_result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found for this device")

    # Mark plant as finished
    plant.end_date = datetime.utcnow()
    plant.status = 'finished'

    if plant.current_phase == 'curing' and not plant.cure_end_date:
        plant.cure_end_date = datetime.utcnow()

    # End any active phase in history
    active_phase_result = await session.execute(
        select(PhaseHistory).where(
            PhaseHistory.plant_id == plant.id,
            PhaseHistory.ended_at == None
        )
    )
    active_phase = active_phase_result.scalars().first()

    if active_phase:
        active_phase.ended_at = datetime.utcnow()

    # Unassign any active device
    assignment_result = await session.execute(
        select(DeviceAssignment).where(
            DeviceAssignment.plant_id == plant.id,
            DeviceAssignment.removed_at == None
        )
    )
    assignment = assignment_result.scalars().first()

    if assignment:
        assignment.removed_at = datetime.utcnow()

    await session.commit()

    return {"status": "success", "message": f"Plant '{plant.name}' marked as finished"}
