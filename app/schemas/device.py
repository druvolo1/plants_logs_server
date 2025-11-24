"""Device-related Pydantic schemas."""
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime


class DeviceCreate(BaseModel):
    """Device creation schema."""
    device_id: str
    name: Optional[str] = None
    device_type: Optional[str] = 'feeding_system'
    scope: Optional[str] = 'plant'
    location_id: Optional[int] = None


class DeviceUpdate(BaseModel):
    """Device update schema."""
    name: Optional[str] = None
    location_id: Optional[int] = None


class DeviceSettingsUpdate(BaseModel):
    """Device settings update schema."""
    use_fahrenheit: Optional[bool] = None
    update_interval: Optional[int] = None


class AssignedPlantInfo(BaseModel):
    """Assigned plant information."""
    plant_id: str
    name: str
    current_phase: Optional[str]


class DeviceRead(BaseModel):
    """Device read schema."""
    device_id: str
    name: Optional[str]
    system_name: Optional[str]
    is_online: bool
    device_type: Optional[str] = 'feeding_system'
    scope: Optional[str] = 'plant'
    capabilities: Optional[str] = None
    last_seen: Optional[datetime] = None
    location_id: Optional[int] = None
    is_owner: Optional[bool] = True
    permission_level: Optional[str] = None
    shared_by_email: Optional[str] = None
    assigned_plants: List[AssignedPlantInfo] = []
    assigned_plant_count: int = 0
    # Legacy fields
    active_plant_name: Optional[str] = None
    active_plant_id: Optional[str] = None
    active_phase: Optional[str] = None


class ShareCreate(BaseModel):
    """Share creation schema."""
    permission_level: str
    expires_in_days: Optional[int] = 7


class ShareAccept(BaseModel):
    """Share acceptance schema."""
    share_code: str


class ShareUpdate(BaseModel):
    """Share update schema."""
    permission_level: str


class ShareRead(BaseModel):
    """Share read schema."""
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
    """Device pairing request schema."""
    device_id: str
    device_name: str
    location_id: Optional[int] = None
    location_name: Optional[str] = None
    mac_address: str
    model: str
    manufacturer: str
    sw_version: str
    hw_version: str


class DevicePairResponse(BaseModel):
    """Device pairing response schema."""
    success: bool
    api_key: str
    device_id: str
    server_url: str
    message: str


class DeviceSettingsResponse(BaseModel):
    """Device settings response schema."""
    use_fahrenheit: bool
    update_interval: int
