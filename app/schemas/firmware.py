# app/schemas/firmware.py
"""
Firmware-related Pydantic schemas.
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class FirmwareCreate(BaseModel):
    """Schema for creating a new firmware record (metadata only, file uploaded separately)."""
    device_type: str
    version: str
    release_notes: Optional[str] = None
    is_prerelease: bool = False


class FirmwareRead(BaseModel):
    """Schema for reading firmware information."""
    id: int
    device_type: str
    version: str
    release_notes: Optional[str]
    file_size: Optional[int]
    checksum: Optional[str]
    is_latest: bool
    is_prerelease: bool
    created_at: datetime

    class Config:
        from_attributes = True


class FirmwareListItem(BaseModel):
    """Condensed firmware info for list views."""
    id: int
    device_type: str
    version: str
    is_latest: bool
    is_prerelease: bool
    file_size: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class DeviceFirmwareAssignmentCreate(BaseModel):
    """Schema for assigning a firmware to a device."""
    device_id: str  # device_id string, not internal id
    firmware_id: int
    force_update: bool = False
    notes: Optional[str] = None


class DeviceFirmwareAssignmentRead(BaseModel):
    """Schema for reading a firmware assignment."""
    id: int
    device_id: int
    firmware_id: int
    force_update: bool
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    # Nested info
    firmware_version: Optional[str] = None
    firmware_device_type: Optional[str] = None
    device_identifier: Optional[str] = None
    device_name: Optional[str] = None
    device_current_firmware: Optional[str] = None  # Device's reported firmware version
    device_is_online: bool = False  # Device online status

    class Config:
        from_attributes = True


class FirmwareUpdateInfo(BaseModel):
    """
    Firmware update information returned in heartbeat response.
    """
    update_available: bool
    current_version: Optional[str] = None
    latest_version: Optional[str] = None
    firmware_url: Optional[str] = None
    release_notes: Optional[str] = None
    force_update: bool = False
    file_size: Optional[int] = None
    checksum: Optional[str] = None
