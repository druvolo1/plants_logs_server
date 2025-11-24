"""Device-related models."""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class Device(Base):
    """Device model."""
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(36), unique=True, index=True)
    api_key = Column(String(64))
    name = Column(String(255), nullable=True)  # User-set custom name
    system_name = Column(String(255), nullable=True)  # Device's self-reported name
    is_online = Column(Boolean, default=False)
    last_seen = Column(DateTime, nullable=True)  # Last connection timestamp
    device_type = Column(String(50), nullable=True, default='feeding_system')
    scope = Column(String(20), nullable=True, default='plant')  # 'plant' (1-to-1) or 'room' (1-to-many)
    capabilities = Column(Text, nullable=True)  # JSON string of device capabilities
    settings = Column(Text, nullable=True)  # JSON string for device-specific settings
    user_id = Column(Integer, ForeignKey("users.id"))
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)

    # Relationships
    user = relationship("User", back_populates="devices")
    location = relationship("Location", back_populates="devices")
    plants = relationship("Plant", foreign_keys="Plant.device_id", cascade="all, delete-orphan", passive_deletes=False)
    device_assignments = relationship("DeviceAssignment", back_populates="device", cascade="all, delete-orphan")


class DeviceShare(Base):
    """Device sharing model."""
    __tablename__ = "device_shares"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
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


class DeviceAssignment(Base):
    """Device assignment model - tracks which device is monitoring which plant."""
    __tablename__ = "device_assignments"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    removed_at = Column(DateTime, nullable=True)  # NULL if still assigned

    # Relationships
    plant = relationship("Plant", back_populates="device_assignments")
    device = relationship("Device", back_populates="device_assignments")
