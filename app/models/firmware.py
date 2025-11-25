# app/models/firmware.py
"""
Firmware management models for OTA updates.
"""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text, BigInteger
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class Firmware(Base):
    """
    Stores firmware versions for different device types.

    Each record represents a firmware binary that can be deployed to devices.
    """
    __tablename__ = "firmware"
    id = Column(Integer, primary_key=True, index=True)

    # Device type this firmware is for (e.g., 'environmental', 'valve_controller', 'feeding_system')
    device_type = Column(String(50), nullable=False, index=True)

    # Semantic version (e.g., "2.1.0", "2.2.0-beta.1")
    version = Column(String(32), nullable=False)

    # Release notes (markdown supported)
    release_notes = Column(Text, nullable=True)

    # Path to the firmware binary file on the server (relative to firmware storage dir)
    file_path = Column(String(512), nullable=False)

    # File size in bytes (for download progress)
    file_size = Column(BigInteger, nullable=True)

    # SHA256 checksum for integrity verification
    checksum = Column(String(64), nullable=True)

    # Is this the "latest" stable release for this device type?
    is_latest = Column(Boolean, default=False, nullable=False)

    # Is this a beta/pre-release version?
    is_prerelease = Column(Boolean, default=False, nullable=False)

    # Who uploaded this firmware
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_user_id])

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Unique constraint on device_type + version
    __table_args__ = (
        # Index for quick lookup of latest firmware per device type
        # UniqueConstraint handled via unique index in migration
    )


class DeviceFirmwareAssignment(Base):
    """
    Assigns specific firmware versions to specific devices.

    Used for:
    - Testing beta firmware on specific devices
    - Rolling back a device to an older version
    - Holding a device at a specific version (skip auto-updates)

    If a device has an assignment, it uses that firmware instead of the "latest" for its type.
    """
    __tablename__ = "device_firmware_assignments"
    id = Column(Integer, primary_key=True, index=True)

    # The device being assigned
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, unique=True)
    device = relationship("Device", foreign_keys=[device_id])

    # The specific firmware version assigned
    firmware_id = Column(Integer, ForeignKey("firmware.id", ondelete="CASCADE"), nullable=False)
    firmware = relationship("Firmware", foreign_keys=[firmware_id])

    # Should this device be forced to update on next heartbeat?
    force_update = Column(Boolean, default=False, nullable=False)

    # Who made this assignment
    assigned_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_by = relationship("User", foreign_keys=[assigned_by_user_id])

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Notes about why this assignment was made (e.g., "Testing new humidity calibration")
    notes = Column(Text, nullable=True)
