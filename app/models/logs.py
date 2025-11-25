# app/models/logs.py
"""
Log entry and environment log models.
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class LogEntry(Base):
    """
    Device-centric log entries. Data is stored once per device reading,
    then associated to plants via DeviceAssignment history when generating reports.
    """
    __tablename__ = "log_entries"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True, index=True)  # Nullable for legacy data
    # Legacy field - kept for backward compatibility with old data
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=True, index=True)
    event_type = Column(String(20), nullable=False)  # 'sensor' or 'dosing'
    sensor_name = Column(String(50), nullable=True)  # e.g., 'ph', 'ec', 'humidity', 'temperature'
    value = Column(Float, nullable=True)  # pH reading, humidity %, temp, etc.
    dose_type = Column(String(10), nullable=True)  # 'up' or 'down'
    dose_amount_ml = Column(Float, nullable=True)  # Dose amount
    timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    device = relationship("Device")
    plant = relationship("Plant")  # Legacy relationship for querying old data


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


class PlantReport(Base):
    """
    Frozen report generated when a plant is marked as finished.
    Contains all raw data points and aggregated stats as JSON.
    This allows purging of raw log data while preserving complete plant history.
    """
    __tablename__ = "plant_reports"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False, unique=True)

    # Report metadata
    generated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    report_version = Column(Integer, nullable=False, default=1)  # For future schema migrations

    # Plant snapshot at time of report (denormalized for historical accuracy)
    plant_name = Column(String(255), nullable=False)
    strain = Column(String(255), nullable=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    final_phase = Column(String(50), nullable=True)

    # Full raw data as JSON (all log entries, env data, etc.)
    # Structure: {
    #   "feeding_logs": [...],
    #   "environment_logs": [...],
    #   "phase_history": [...],
    #   "device_assignments": [...],
    #   "linked_devices": [...]
    # }
    raw_data = Column(Text, nullable=False)  # JSON blob

    # Aggregated statistics as JSON
    # Structure: {
    #   "ph": {"min": x, "max": y, "avg": z, "readings_count": n},
    #   "ec": {...},
    #   "temperature": {...},
    #   "humidity": {...},
    #   "total_ph_up_ml": x,
    #   "total_ph_down_ml": y,
    #   "dosing_events_count": n,
    #   "days_in_each_phase": {...}
    # }
    aggregated_stats = Column(Text, nullable=True)  # JSON blob

    # Relationships
    plant = relationship("Plant", back_populates="report")
