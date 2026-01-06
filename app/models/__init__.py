# app/models/__init__.py
"""
SQLAlchemy models for the plants logs server.
"""
from .base import Base
from .user import User, OAuthAccount, LoginHistory
from .device import Device, DeviceShare, DeviceLink, DeviceConnection, DeviceDebugLog, DevicePostingSlot
from .location import Location, LocationShare
from .plant import Plant, PhaseTemplate, PhaseHistory, DeviceAssignment
from .logs import PlantDailyLog, PlantReport, DosingEvent
from .firmware import Firmware, DeviceFirmwareAssignment
from .notification import Notification, NotificationSeverity, NotificationStatus

__all__ = [
    "Base",
    "User",
    "OAuthAccount",
    "LoginHistory",
    "Device",
    "DeviceShare",
    "DeviceLink",
    "DeviceConnection",
    "DeviceDebugLog",
    "DevicePostingSlot",
    "Location",
    "LocationShare",
    "Plant",
    "PhaseTemplate",
    "PhaseHistory",
    "DeviceAssignment",
    "PlantDailyLog",
    "PlantReport",
    "DosingEvent",
    "Firmware",
    "DeviceFirmwareAssignment",
    "Notification",
    "NotificationSeverity",
    "NotificationStatus",
]
