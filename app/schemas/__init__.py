"""Pydantic schemas for request/response models."""
from .user import UserRead, UserCreate, UserUpdate, UserLogin, PasswordReset
from .device import (
    DeviceCreate,
    DeviceUpdate,
    DeviceSettingsUpdate,
    AssignedPlantInfo,
    DeviceRead,
    ShareCreate,
    ShareAccept,
    ShareUpdate,
    ShareRead,
    DevicePairRequest,
    DevicePairResponse,
    DeviceSettingsResponse,
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
    PhaseTemplateCreate,
    PhaseTemplateRead,
    PlantCreateNew,
    DeviceAssignmentCreate,
    PlantFinish,
    PlantYieldUpdate,
    AssignedDeviceInfo,
    PlantRead,
    DeviceAssignmentRead,
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
    "DeviceSettingsUpdate",
    "AssignedPlantInfo",
    "DeviceRead",
    "ShareCreate",
    "ShareAccept",
    "ShareUpdate",
    "ShareRead",
    "DevicePairRequest",
    "DevicePairResponse",
    "DeviceSettingsResponse",
    # Location schemas
    "LocationCreate",
    "LocationUpdate",
    "LocationRead",
    "LocationShareCreate",
    "LocationShareRead",
    # Plant schemas
    "PlantCreate",
    "PhaseTemplateCreate",
    "PhaseTemplateRead",
    "PlantCreateNew",
    "DeviceAssignmentCreate",
    "PlantFinish",
    "PlantYieldUpdate",
    "AssignedDeviceInfo",
    "PlantRead",
    "DeviceAssignmentRead",
    # Log schemas
    "LogEntryCreate",
    "LogEntryRead",
    "EnvironmentDataCreate",
    "EnvironmentLogRead",
]
