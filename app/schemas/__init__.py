# app/schemas/__init__.py
"""
Pydantic schemas for request/response validation.
"""
from .user import UserRead, UserCreate, UserUpdate, UserLogin, PasswordReset
from .device import (
    DeviceCreate,
    DeviceUpdate,
    DeviceRead,
    DeviceSettingsUpdate,
    DeviceSettingsResponse,
    DevicePairRequest,
    DevicePairResponse,
    AssignedPlantInfo,
    ShareCreate,
    ShareAccept,
    ShareUpdate,
    ShareRead,
    DeviceLinkCreate,
    DeviceLinkRead,
    LinkedDeviceInfo,
    AvailableDeviceForLinking,
)
from .location import (
    LocationCreate,
    LocationUpdate,
    LocationRead,
    LocationShareCreate,
    LocationShareRead,
)
from .plant import (
    PlantCreate,
    PlantCreateNew,
    PlantRead,
    PlantFinish,
    PlantYieldUpdate,
    PhaseTemplateCreate,
    PhaseTemplateRead,
    DeviceAssignmentCreate,
    AssignedDeviceInfo,
    PlantAssignmentRead,
    PhaseHistoryRead,
)
from .logs import (
    LogEntryCreate,
    LogEntryRead,
    EnvironmentDataCreate,
    EnvironmentLogRead,
)

__all__ = [
    # User schemas
    "UserRead",
    "UserCreate",
    "UserUpdate",
    "UserLogin",
    "PasswordReset",
    # Device schemas
    "DeviceCreate",
    "DeviceUpdate",
    "DeviceRead",
    "DeviceSettingsUpdate",
    "DeviceSettingsResponse",
    "DevicePairRequest",
    "DevicePairResponse",
    "AssignedPlantInfo",
    "ShareCreate",
    "ShareAccept",
    "ShareUpdate",
    "ShareRead",
    "DeviceLinkCreate",
    "DeviceLinkRead",
    "LinkedDeviceInfo",
    "AvailableDeviceForLinking",
    # Location schemas
    "LocationCreate",
    "LocationUpdate",
    "LocationRead",
    "LocationShareCreate",
    "LocationShareRead",
    # Plant schemas
    "PlantCreate",
    "PlantCreateNew",
    "PlantRead",
    "PlantFinish",
    "PlantYieldUpdate",
    "PhaseTemplateCreate",
    "PhaseTemplateRead",
    "DeviceAssignmentCreate",
    "AssignedDeviceInfo",
    "PlantAssignmentRead",
    "PhaseHistoryRead",
    # Log schemas
    "LogEntryCreate",
    "LogEntryRead",
    "EnvironmentDataCreate",
    "EnvironmentLogRead",
]
