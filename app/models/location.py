# app/models/location.py
"""
Location and location sharing models.
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class Location(Base):
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    parent_id = Column(Integer, ForeignKey("locations.id"), nullable=True)  # NULL for top-level locations
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Owner of the location
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    parent = relationship("Location", remote_side=[id], backref="children")
    owner = relationship("User", foreign_keys=[user_id])
    devices = relationship("Device", back_populates="location")
    plants = relationship("Plant", back_populates="location")
    location_shares = relationship("LocationShare", foreign_keys="LocationShare.location_id", cascade="all, delete-orphan")


class LocationShare(Base):
    __tablename__ = "location_shares"
    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
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
    location = relationship("Location", foreign_keys=[location_id])
    owner = relationship("User", foreign_keys=[owner_user_id])
    shared_with = relationship("User", foreign_keys=[shared_with_user_id])
