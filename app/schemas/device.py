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
    update_interval: Optional[int] = None  # Heartbeat interval in seconds
    log_interval: Optional[int] = None  # Database logging interval in seconds


class LinkedDeviceInfo(BaseModel):
    """Summary info about a linked device for inclusion in DeviceRead"""
    device_id: str
    name: Optional[str] = None
    system_name: Optional[str] = None
    device_type: Optional[str] = None
    is_online: bool = False
    link_type: str
    is_location_inherited: bool


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
    # Linked devices (env sensors, valve controllers linked to this feeding system)
    linked_devices: List[LinkedDeviceInfo] = []
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
    update_interval: int  # Heartbeat interval in seconds (default: 30)
    log_interval: int  # Database logging interval in seconds (default: 3600 = 1 hour)


# Device Linking Pydantic models
class DeviceLinkCreate(BaseModel):
    """Create a link between a feeding system and an env sensor or valve controller"""
    child_device_id: str  # The device_id (UUID) of the device to link
    link_type: str  # 'environmental' or 'valve_controller'


class DeviceLinkRead(BaseModel):
    """Read model for device links"""
    id: int
    link_type: str  # 'environmental' or 'valve_controller'
    is_location_inherited: bool
    created_at: datetime
    # Child device info
    child_device_id: str  # UUID
    child_device_name: Optional[str] = None
    child_device_system_name: Optional[str] = None
    child_device_type: Optional[str] = None
    child_device_is_online: bool = False


class AvailableDeviceForLinking(BaseModel):
    """Device that can be linked to a feeding system"""
    device_id: str
    name: Optional[str] = None
    system_name: Optional[str] = None
    device_type: str
    is_online: bool = False
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    is_same_location: bool = False  # True if in same location as parent device
