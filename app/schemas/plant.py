# app/schemas/plant.py
"""
Plant-related Pydantic schemas.
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class PlantCreate(BaseModel):
    name: str  # Strain name
    system_id: Optional[str] = None
    device_id: str  # Device UUID
    location_id: Optional[int] = None  # Location assignment


class PhaseTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    expected_seed_days: Optional[int] = None
    expected_clone_days: Optional[int] = None
    expected_veg_days: Optional[int] = None
    expected_flower_days: Optional[int] = None
    expected_drying_days: Optional[int] = None
    expected_curing_days: Optional[int] = None


class PhaseTemplateRead(BaseModel):
    id: int
    name: str
    description: Optional[str]
    expected_seed_days: Optional[int]
    expected_clone_days: Optional[int]
    expected_veg_days: Optional[int]
    expected_flower_days: Optional[int]
    expected_drying_days: Optional[int]
    expected_curing_days: Optional[int]

    class Config:
        from_attributes = True


class PlantCreateNew(BaseModel):
    """New plant creation without device assignment"""
    name: str  # Strain name
    batch_number: Optional[str] = None  # Batch number for seed-to-sale tracking
    location_id: Optional[int] = None  # Location assignment
    starting_phase: Optional[str] = 'seed'  # Initial phase: 'seed', 'clone', 'veg', 'flower', 'drying', 'curing'
    template_id: Optional[int] = None  # Phase template to use


class DeviceAssignmentCreate(BaseModel):
    """Assign a device to a plant (phase is tracked separately on the plant)"""
    device_id: str  # Device UUID


class PlantFinish(BaseModel):
    end_date: Optional[str] = None  # ISO format date string, defaults to today


class PlantYieldUpdate(BaseModel):
    yield_grams: float


class AssignedDeviceInfo(BaseModel):
    """Info about a device assigned to a plant"""
    device_id: str  # Device UUID
    device_name: Optional[str]
    system_name: Optional[str]
    is_online: bool


class PlantRead(BaseModel):
    id: int
    plant_id: str
    name: str
    batch_number: Optional[str]
    system_id: Optional[str]
    device_id: Optional[str]  # Device UUID for display (legacy, may be None for new plants)
    device_name: Optional[str]  # Device name for display
    location_id: Optional[int]
    start_date: datetime
    end_date: Optional[datetime]
    yield_grams: Optional[float]
    status: str  # 'created', 'feeding', 'harvested', 'curing', 'finished'
    current_phase: Optional[str]  # Current phase name
    harvest_date: Optional[datetime]
    cure_start_date: Optional[datetime]
    cure_end_date: Optional[datetime]
    # Expected phase durations
    expected_seed_days: Optional[int]
    expected_clone_days: Optional[int]
    expected_veg_days: Optional[int]
    expected_flower_days: Optional[int]
    expected_drying_days: Optional[int]
    expected_curing_days: Optional[int]
    template_id: Optional[int]
    is_active: bool = True  # Computed field: True if status != 'finished'
    assigned_devices: Optional[list] = []  # List of assigned devices with status

    class Config:
        from_attributes = True


class PlantAssignmentRead(BaseModel):
    """Read schema for plant-device assignments"""
    id: int
    plant_id: str  # Plant UUID
    device_id: str  # Device UUID
    device_name: Optional[str]
    system_name: Optional[str]  # Device's self-reported name
    phase: Optional[str]  # Phase when assignment started
    assigned_at: datetime
    removed_at: Optional[datetime]
    is_active: bool

    class Config:
        from_attributes = True


class PhaseHistoryRead(BaseModel):
    """Read schema for plant phase history"""
    id: int
    plant_id: str  # Plant UUID
    phase: str
    started_at: datetime
    ended_at: Optional[datetime]
    duration_days: Optional[int]

    class Config:
        from_attributes = True
