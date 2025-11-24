# app/models/logs.py
"""
Log entry and environment log models.
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class LogEntry(Base):
    __tablename__ = "log_entries"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    event_type = Column(String(20), nullable=False)  # 'sensor' or 'dosing'
    sensor_name = Column(String(50), nullable=True)  # e.g., 'ph', 'ec', 'humidity', 'temperature'
    value = Column(Float, nullable=True)  # pH reading, humidity %, temp, etc.
    dose_type = Column(String(10), nullable=True)  # 'up' or 'down'
    dose_amount_ml = Column(Float, nullable=True)  # Dose amount
    timestamp = Column(DateTime, nullable=False, index=True)
    phase = Column(String(50), nullable=True)  # 'feeding', 'curing', etc. - which phase this log is from

    # Relationships
    plant = relationship("Plant", back_populates="logs")


class EnvironmentLog(Base):
    __tablename__ = "environment_logs"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)

    # Air Quality readings
    co2 = Column(Integer, nullable=True)
    temperature = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)
    vpd = Column(Float, nullable=True)

    # Atmospheric readings
    pressure = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)
    gas_resistance = Column(Float, nullable=True)
    air_quality_score = Column(Integer, nullable=True)

    # Light readings
    lux = Column(Float, nullable=True)
    ppfd = Column(Float, nullable=True)

    timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    device = relationship("Device")
    location = relationship("Location")
