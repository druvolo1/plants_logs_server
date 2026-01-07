# app/models/logs.py
"""
Plant-centric daily log models.
"""
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float, Text, Date, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, date
from .base import Base


class PlantDailyLog(Base):
    """
    Plant-centric daily aggregated logs.
    One row per plant per day with min/max/avg for all sensor readings.
    Data is written directly to plants when devices post readings.
    """
    __tablename__ = "plant_daily_logs"

    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False, index=True)
    log_date = Column(Date, nullable=False, index=True)

    # Hydroponic data (min/max/avg for daily aggregation)
    ph_min = Column(Float, nullable=True)
    ph_max = Column(Float, nullable=True)
    ph_avg = Column(Float, nullable=True)

    ec_min = Column(Float, nullable=True)
    ec_max = Column(Float, nullable=True)
    ec_avg = Column(Float, nullable=True)

    tds_min = Column(Float, nullable=True)
    tds_max = Column(Float, nullable=True)
    tds_avg = Column(Float, nullable=True)

    water_temp_min = Column(Float, nullable=True)
    water_temp_max = Column(Float, nullable=True)
    water_temp_avg = Column(Float, nullable=True)

    # Dosing totals for the day
    total_ph_up_ml = Column(Float, nullable=True, default=0.0)
    total_ph_down_ml = Column(Float, nullable=True, default=0.0)
    dosing_events_count = Column(Integer, nullable=True, default=0)

    # Environmental data (min/max/avg for daily aggregation)
    co2_min = Column(Integer, nullable=True)
    co2_max = Column(Integer, nullable=True)
    co2_avg = Column(Float, nullable=True)

    air_temp_min = Column(Float, nullable=True)
    air_temp_max = Column(Float, nullable=True)
    air_temp_avg = Column(Float, nullable=True)

    humidity_min = Column(Float, nullable=True)
    humidity_max = Column(Float, nullable=True)
    humidity_avg = Column(Float, nullable=True)

    vpd_min = Column(Float, nullable=True)
    vpd_max = Column(Float, nullable=True)
    vpd_avg = Column(Float, nullable=True)

    # Light tracking (based on threshold crossings)
    total_light_seconds = Column(Integer, nullable=True)  # Total seconds lights were ON
    light_cycles_count = Column(Integer, nullable=True)  # Number of ON/OFF cycles
    longest_light_period_seconds = Column(Integer, nullable=True)  # Longest continuous ON period
    shortest_light_period_seconds = Column(Integer, nullable=True)  # Shortest continuous ON period

    # Metadata
    hydro_device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    env_device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    last_hydro_reading = Column(DateTime, nullable=True)
    last_env_reading = Column(DateTime, nullable=True)
    readings_count = Column(Integer, nullable=True, default=0)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Ensure one row per plant per day
    __table_args__ = (
        UniqueConstraint('plant_id', 'log_date', name='uq_plant_date'),
    )

    # Relationships
    plant = relationship("Plant")
    hydro_device = relationship("Device", foreign_keys=[hydro_device_id])
    env_device = relationship("Device", foreign_keys=[env_device_id])


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


class DosingEvent(Base):
    """
    Individual dosing events from hydro controllers.
    Tracks each time the controller adjusted pH or added nutrients.
    """
    __tablename__ = "dosing_events"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    event_date = Column(Date, nullable=False, index=True)  # Date for quick daily queries
    timestamp = Column(DateTime, nullable=False)  # Exact time of dosing event
    dosing_type = Column(String(50), nullable=False)  # 'ph_up', 'ph_down', 'nutrient_a', 'nutrient_b', etc.
    amount_ml = Column(Float, nullable=False)  # Amount dosed in milliliters
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Indexes for efficient queries
    __table_args__ = (
        UniqueConstraint('plant_id', 'timestamp', 'dosing_type', name='uq_plant_timestamp_type'),
    )

    # Relationships
    plant = relationship("Plant")
    device = relationship("Device")


class LightEvent(Base):
    """
    Individual light ON/OFF events from environment sensors.
    Tracks each time lights crossed the threshold (ON or OFF).
    """
    __tablename__ = "light_events"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    event_date = Column(Date, nullable=False, index=True)  # Date for quick daily queries
    start_time = Column(DateTime, nullable=False)  # When lights came ON
    end_time = Column(DateTime, nullable=False)  # When lights went OFF
    duration_seconds = Column(Integer, nullable=False)  # How long lights were ON
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Indexes for efficient queries
    __table_args__ = (
        UniqueConstraint('plant_id', 'start_time', name='uq_plant_start_time'),
    )

    # Relationships
    plant = relationship("Plant")
    device = relationship("Device")
