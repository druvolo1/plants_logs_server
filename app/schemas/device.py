# app/schemas/device.py
"""
Device-related Pydantic schemas.
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class AssignedPlantInfo(BaseModel):
    plant_id: str
    name: str
    current_phase: Optional[str]


class DeviceCreate(BaseModel):
    device_id: str
    name: Optional[str] = None
    device_type: Optional[str] = 'feeding_system'  # 'feeding_system', 'environmental', 'valve_controller', 'other'
    scope: Optional[str] = 'plant'  # 'plant' or 'room'
    location_id: Optional[int] = None  # Location assignment


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    location_id: Optional[int] = None


class DeviceSettingsUpdate(BaseModel):
    use_fahrenheit: Optional[bool] = None
    update_interval: Optional[int] = None


class DeviceRead(BaseModel):
    device_id: str
    name: Optional[str] = None  # User-set custom name
    system_name: Optional[str] = None  # Device's self-reported name
    is_online: bool
    device_type: Optional[str] = 'feeding_system'  # Device type
    scope: Optional[str] = 'plant'  # 'plant' or 'room'
    capabilities: Optional[str] = None  # JSON string of capabilities
    last_seen: Optional[datetime] = None  # Last connection timestamp
    location_id: Optional[int] = None  # Location assignment
    is_owner: Optional[bool] = True  # Whether current user owns the device
    permission_level: Optional[str] = None  # 'viewer', 'controller', or None if owner
    shared_by_email: Optional[str] = None  # Email of owner if shared device
    assigned_plants: List[AssignedPlantInfo] = []  # All plants currently assigned to device
    assigned_plant_count: int = 0  # Count of assigned plants
    # Legacy fields (kept for backward compatibility)
    active_plant_name: Optional[str] = None  # Name of first assigned plant
    active_plant_id: Optional[str] = None  # ID of first assigned plant
    active_phase: Optional[str] = None  # Phase of first assigned plant


# Device Sharing Pydantic models
class ShareCreate(BaseModel):
    permission_level: str  # 'viewer' or 'controller'
    expires_in_days: Optional[int] = 7  # None for never expire


class ShareAccept(BaseModel):
    share_code: str


class ShareUpdate(BaseModel):
    permission_level: str


class ShareRead(BaseModel):
    id: int
    device_id: int
    share_code: str
    permission_level: str
    created_at: datetime
    expires_at: datetime
    accepted_at: Optional[datetime]
    is_active: bool
    shared_with_email: Optional[str]


class DevicePairRequest(BaseModel):
    device_id: str
    device_name: str
    location_id: Optional[int] = None
    location_name: Optional[str] = None  # For creating new location
    # Device info
    mac_address: str
    model: str
    manufacturer: str
    sw_version: str
    hw_version: str


class DevicePairResponse(BaseModel):
    success: bool
    api_key: str
    device_id: str
    server_url: str
    message: str


class DeviceSettingsResponse(BaseModel):
    use_fahrenheit: bool
    update_interval: int  # seconds
