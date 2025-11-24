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
    start_date: Optional[str] = None  # ISO format, defaults to now
    phase: Optional[str] = 'clone'  # Initial phase: 'seed', 'clone', 'veg', 'flower', 'drying', 'curing'
    template_id: Optional[int] = None  # Phase template to use
    # Expected durations (override template if provided)
    expected_seed_days: Optional[int] = None
    expected_clone_days: Optional[int] = None
    expected_veg_days: Optional[int] = None
    expected_flower_days: Optional[int] = None
    expected_drying_days: Optional[int] = None
    expected_curing_days: Optional[int] = None


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
    plant_id: str
    name: str
    batch_number: Optional[str]
    system_id: Optional[str]
    device_id: Optional[str]  # Device UUID for display (legacy, may be None for new plants)
    start_date: datetime
    end_date: Optional[datetime]
    yield_grams: Optional[float]
    is_active: bool  # Computed: True if end_date is None
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
    assigned_devices: List['AssignedDeviceInfo'] = []  # Currently assigned devices


class DeviceAssignmentRead(BaseModel):
    id: int
    device_id: str  # Device UUID
    device_name: Optional[str]
    phase: str
    assigned_at: datetime
    removed_at: Optional[datetime]
