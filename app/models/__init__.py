# app/models/__init__.py
"""
SQLAlchemy models for the plants logs server.
"""
from .base import Base
from .user import User, OAuthAccount
from .device import Device, DeviceShare, DeviceLink
from .location import Location, LocationShare
from .plant import Plant, PhaseTemplate, PhaseHistory, DeviceAssignment
from .logs import LogEntry, EnvironmentLog, PlantReport
from .firmware import Firmware, DeviceFirmwareAssignment

__all__ = [
    "Base",
    "User",
    "OAuthAccount",
    "Device",
    "DeviceShare",
    "DeviceLink",
    "Location",
    "LocationShare",
    "Plant",
    "PhaseTemplate",
    "PhaseHistory",
    "DeviceAssignment",
    "LogEntry",
    "EnvironmentLog",
    "PlantReport",
    "Firmware",
    "DeviceFirmwareAssignment",
]
