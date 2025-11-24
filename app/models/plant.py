# app/models/plant.py
"""
Plant, phase template, phase history, and device assignment models.
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class PhaseTemplate(Base):
    __tablename__ = "phase_templates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Expected durations for each phase (in days)
    expected_seed_days = Column(Integer, nullable=True)
    expected_clone_days = Column(Integer, nullable=True)
    expected_veg_days = Column(Integer, nullable=True)
    expected_flower_days = Column(Integer, nullable=True)
    expected_drying_days = Column(Integer, nullable=True)
    expected_curing_days = Column(Integer, nullable=True)

    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=True)


class Plant(Base):
    __tablename__ = "plants"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(String(64), unique=True, index=True, nullable=False)  # Timestamp-based unique ID
    name = Column(String(255), nullable=False)  # Strain name
    batch_number = Column(String(100), nullable=True)  # Batch number for seed-to-sale tracking
    system_id = Column(String(255), nullable=True)  # e.g., "Zone1" - legacy field, use device_assignments for new plants
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)  # Made nullable - legacy field for backward compatibility
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)  # Location assignment
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    yield_grams = Column(Float, nullable=True)  # Added after harvest
    display_order = Column(Integer, nullable=True, default=0)  # For user-defined ordering

    # New lifecycle fields
    status = Column(String(50), nullable=False, default='created')  # 'created', 'feeding', 'harvested', 'curing', 'finished'
    current_phase = Column(String(50), nullable=True)  # Current phase name, e.g., 'feeding', 'curing'
    harvest_date = Column(DateTime, nullable=True)  # When plant was harvested from feeding
    cure_start_date = Column(DateTime, nullable=True)  # When curing phase started
    cure_end_date = Column(DateTime, nullable=True)  # When curing phase completed

    # Expected phase durations (in days) - can override template
    expected_seed_days = Column(Integer, nullable=True)
    expected_clone_days = Column(Integer, nullable=True)
    expected_veg_days = Column(Integer, nullable=True)
    expected_flower_days = Column(Integer, nullable=True)
    expected_drying_days = Column(Integer, nullable=True)
    expected_curing_days = Column(Integer, nullable=True)
    template_id = Column(Integer, ForeignKey("phase_templates.id"), nullable=True)

    # Relationships
    device = relationship("Device", foreign_keys=[device_id], back_populates="plants")
    user = relationship("User", foreign_keys=[user_id])
    location = relationship("Location", back_populates="plants")
    logs = relationship("LogEntry", back_populates="plant", cascade="all, delete-orphan")
    device_assignments = relationship("DeviceAssignment", back_populates="plant", cascade="all, delete-orphan")
    phase_history = relationship("PhaseHistory", back_populates="plant", cascade="all, delete-orphan")


class DeviceAssignment(Base):
    __tablename__ = "device_assignments"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    removed_at = Column(DateTime, nullable=True)  # NULL if still assigned

    # Relationships
    plant = relationship("Plant", back_populates="device_assignments")
    device = relationship("Device", back_populates="device_assignments")


class PhaseHistory(Base):
    __tablename__ = "phase_history"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    phase = Column(String(50), nullable=False)  # 'clone', 'veg', 'flower', 'drying'
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)  # NULL if current phase

    # Relationships
    plant = relationship("Plant", back_populates="phase_history")
