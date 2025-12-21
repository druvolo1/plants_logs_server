# app/models/device.py
"""
Device and device sharing models.
"""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(36), unique=True, index=True)
    api_key = Column(String(64))
    name = Column(String(255), nullable=True)  # User-set custom name
    system_name = Column(String(255), nullable=True)  # Device's self-reported name
    is_online = Column(Boolean, default=False)
    last_seen = Column(DateTime, nullable=True)  # Last connection timestamp
    device_type = Column(String(50), nullable=True, default='feeding_system')  # 'feeding_system', 'environmental', 'valve_controller', 'other'
    scope = Column(String(20), nullable=True, default='plant')  # 'plant' (1-to-1) or 'room' (1-to-many)
    firmware_version = Column(String(50), nullable=True)  # Current firmware version reported by device
    mdns_hostname = Column(String(255), nullable=True)  # mDNS hostname (e.g., "herbnerdz-valve.local")
    ip_address = Column(String(45), nullable=True)  # Current IP address (IPv4 or IPv6)
    capabilities = Column(Text, nullable=True)  # JSON string of device capabilities
    settings = Column(Text, nullable=True)  # JSON string for device-specific settings (temp scale, update interval, etc.)
    user_id = Column(Integer, ForeignKey("users.id"))
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)  # Location assignment
    user = relationship("User", back_populates="devices")
    location = relationship("Location", back_populates="devices")
    plants = relationship("Plant", foreign_keys="Plant.device_id", cascade="all, delete-orphan", passive_deletes=False)
    device_assignments = relationship("DeviceAssignment", back_populates="device", cascade="all, delete-orphan")

    # Device linking relationships (for feeding_system as parent)
    linked_child_devices = relationship(
        "DeviceLink",
        foreign_keys="DeviceLink.parent_device_id",
        back_populates="parent_device",
        cascade="all, delete-orphan"
    )
    # Device linking relationships (for env sensors/valve controllers as child)
    linked_parent_devices = relationship(
        "DeviceLink",
        foreign_keys="DeviceLink.child_device_id",
        back_populates="child_device",
        cascade="all, delete-orphan"
    )


class DeviceShare(Base):
    __tablename__ = "device_shares"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    shared_with_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL until accepted
    share_code = Column(String(12), unique=True, index=True, nullable=False)
    permission_level = Column(String(20), nullable=False)  # 'viewer' or 'controller'
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)  # NULL for never expire
    accepted_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    device = relationship("Device", foreign_keys=[device_id])
    owner = relationship("User", foreign_keys=[owner_user_id])
    shared_with = relationship("User", foreign_keys=[shared_with_user_id])


class DeviceLink(Base):
    """
    Links devices together. Used to associate environmental sensors and valve controllers
    with feeding systems.

    - parent_device: The feeding_system that acts as the hub
    - child_device: The environmental sensor or valve controller being linked
    - link_type: 'environmental' or 'valve_controller'
    - is_location_inherited: True if auto-linked based on location hierarchy, False if explicitly linked
    """
    __tablename__ = "device_links"
    id = Column(Integer, primary_key=True, index=True)
    parent_device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    child_device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    link_type = Column(String(30), nullable=False)  # 'environmental', 'valve_controller'
    is_location_inherited = Column(Boolean, default=False, nullable=False)  # True = auto from location, False = explicit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    removed_at = Column(DateTime, nullable=True)  # NULL = active link, set when link is removed for history tracking

    # Relationships
    parent_device = relationship("Device", foreign_keys=[parent_device_id], back_populates="linked_child_devices")
    child_device = relationship("Device", foreign_keys=[child_device_id], back_populates="linked_parent_devices")


class DeviceDebugLog(Base):
    """
    Stores metadata for debug log captures from devices.
    Actual log content is stored in filesystem at logs/{device_id}/{filename}.
    """
    __tablename__ = "device_debug_logs"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)  # e.g., "2024-01-15_14-30-00.txt"
    requested_duration = Column(Integer, nullable=False)  # Duration requested in seconds
    actual_duration = Column(Integer, nullable=True)  # Actual capture duration in seconds
    file_size = Column(Integer, nullable=True)  # Size in bytes
    early_cutoff_reason = Column(String(255), nullable=True)  # e.g., "low_memory", "buffer_full", null if completed normally
    status = Column(String(20), nullable=False, default='pending')  # 'pending', 'capturing', 'completed', 'failed'
    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)  # When device started capturing
    completed_at = Column(DateTime, nullable=True)  # When log was uploaded
    requested_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    device = relationship("Device", foreign_keys=[device_id])
    requested_by = relationship("User", foreign_keys=[requested_by_user_id])
