"""Plant-related Pydantic schemas."""
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime


class PlantCreate(BaseModel):
    """Plant creation schema (legacy)."""
    name: str
    system_id: Optional[str] = None
    device_id: str
    location_id: Optional[int] = None


class PhaseTemplateCreate(BaseModel):
    """Phase template creation schema."""
    name: str
    description: Optional[str] = None
    expected_seed_days: Optional[int] = None
    expected_clone_days: Optional[int] = None
    expected_veg_days: Optional[int] = None
    expected_flower_days: Optional[int] = None
    expected_drying_days: Optional[int] = None
    expected_curing_days: Optional[int] = None


class PhaseTemplateRead(BaseModel):
    """Phase template read schema."""
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
    """New plant creation schema."""
    name: str
    batch_number: Optional[str] = None
    start_date: Optional[str] = None
    phase: Optional[str] = 'clone'
    template_id: Optional[int] = None
    expected_seed_days: Optional[int] = None
    expected_clone_days: Optional[int] = None
    expected_veg_days: Optional[int] = None
    expected_flower_days: Optional[int] = None
    expected_drying_days: Optional[int] = None
    expected_curing_days: Optional[int] = None


class DeviceAssignmentCreate(BaseModel):
    """Device assignment creation schema."""
    device_id: str


class PlantFinish(BaseModel):
    """Plant finish schema."""
    end_date: Optional[str] = None


class PlantYieldUpdate(BaseModel):
    """Plant yield update schema."""
    yield_grams: float


class AssignedDeviceInfo(BaseModel):
    """Assigned device information."""
    device_id: str
    device_name: Optional[str]
    system_name: Optional[str]
    is_online: bool


class PlantRead(BaseModel):
    """Plant read schema."""
    plant_id: str
    name: str
    batch_number: Optional[str]
    system_id: Optional[str]
    device_id: Optional[str]
    start_date: datetime
    end_date: Optional[datetime]
    yield_grams: Optional[float]
    is_active: bool
    status: str
    current_phase: Optional[str]
    harvest_date: Optional[datetime]
    cure_start_date: Optional[datetime]
    cure_end_date: Optional[datetime]
    expected_seed_days: Optional[int]
    expected_clone_days: Optional[int]
    expected_veg_days: Optional[int]
    expected_flower_days: Optional[int]
    expected_drying_days: Optional[int]
    expected_curing_days: Optional[int]
    template_id: Optional[int]
    assigned_devices: List['AssignedDeviceInfo'] = []


class DeviceAssignmentRead(BaseModel):
    """Device assignment read schema."""
    id: int
    device_id: str
    device_name: Optional[str]
    phase: str
    assigned_at: datetime
    removed_at: Optional[datetime]
