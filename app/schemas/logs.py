# app/schemas/logs.py
"""
Plant-centric logging Pydantic schemas.
"""
from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, field_validator


class HydroReadingCreate(BaseModel):
    """Schema for hydro controller posting sensor readings (4x/day)"""
    # Device info
    firmware_version: Optional[str] = None
    mdns_hostname: Optional[str] = None
    ip_address: Optional[str] = None

    # Hydro sensor data
    ph: Optional[float] = None
    ec: Optional[float] = None
    tds: Optional[float] = None
    water_temp: Optional[float] = None

    # Dosing data
    dose_ph_up_ml: Optional[float] = None
    dose_ph_down_ml: Optional[float] = None

    timestamp: str  # ISO format datetime string

    @field_validator('ph', 'ec', 'tds', 'water_temp', 'dose_ph_up_ml', 'dose_ph_down_ml', mode='before')
    @classmethod
    def parse_value(cls, v):
        """Handle 'N/A' or other non-numeric values gracefully"""
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            if v.lower() in ('n/a', 'na', 'null', 'none', ''):
                return None
            try:
                return float(v)
            except ValueError:
                return None
        return None


class EnvironmentReadingCreate(BaseModel):
    """Schema for environment sensor posting readings (4x/day)"""
    # Device info
    firmware_version: Optional[str] = None
    mdns_hostname: Optional[str] = None
    ip_address: Optional[str] = None

    # Air Quality
    co2: Optional[int] = None
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    vpd: Optional[float] = None

    # Atmospheric
    pressure: Optional[float] = None
    altitude: Optional[float] = None
    gas_resistance: Optional[float] = None
    air_quality_score: Optional[int] = None

    # Light
    lux: Optional[float] = None
    ppfd: Optional[float] = None

    timestamp: str  # ISO format datetime string


# Keep this for backward compatibility with heartbeat endpoint
class EnvironmentDataCreate(EnvironmentReadingCreate):
    """Alias for backward compatibility"""
    pass


class PlantDailyLogRead(BaseModel):
    """Schema for reading plant daily logs"""
    id: int
    plant_id: int
    log_date: date

    # Hydro data
    ph_min: Optional[float]
    ph_max: Optional[float]
    ph_avg: Optional[float]
    ec_min: Optional[float]
    ec_max: Optional[float]
    ec_avg: Optional[float]
    tds_min: Optional[float]
    tds_max: Optional[float]
    tds_avg: Optional[float]
    water_temp_min: Optional[float]
    water_temp_max: Optional[float]
    water_temp_avg: Optional[float]

    # Dosing
    total_ph_up_ml: Optional[float]
    total_ph_down_ml: Optional[float]
    dosing_events_count: Optional[int]

    # Environment data
    co2_min: Optional[int]
    co2_max: Optional[int]
    co2_avg: Optional[float]
    air_temp_min: Optional[float]
    air_temp_max: Optional[float]
    air_temp_avg: Optional[float]
    humidity_min: Optional[float]
    humidity_max: Optional[float]
    humidity_avg: Optional[float]
    vpd_min: Optional[float]
    vpd_max: Optional[float]
    vpd_avg: Optional[float]
    lux_min: Optional[float]
    lux_max: Optional[float]
    lux_avg: Optional[float]
    ppfd_min: Optional[float]
    ppfd_max: Optional[float]
    ppfd_avg: Optional[float]
    light_detected: Optional[bool]

    # Metadata
    hydro_device_id: Optional[int]
    env_device_id: Optional[int]
    readings_count: Optional[int]
    created_at: datetime
    updated_at: datetime


# Daily Report Schemas (for once-daily aggregated posting)

class DosingEventSchema(BaseModel):
    """Individual dosing event within a daily report"""
    timestamp: str  # ISO format datetime string (e.g., "2026-01-06T08:15:30Z")
    type: str  # 'ph_up', 'ph_down', 'nutrient_a', 'nutrient_b', etc.
    amount_ml: float  # Amount dosed in milliliters


class EnvironmentDailyReport(BaseModel):
    """
    Daily aggregated report from environment sensor.
    Device calculates min/max/avg throughout the day and posts once daily.
    """
    report_date: str  # Date in YYYY-MM-DD format
    readings_count: int  # Number of readings aggregated (e.g., 2880 for 30s intervals over 24h)

    # CO2 (ppm)
    co2_min: Optional[int] = None
    co2_max: Optional[int] = None
    co2_avg: Optional[float] = None

    # Temperature (°C or °F depending on device setting)
    temperature_min: Optional[float] = None
    temperature_max: Optional[float] = None
    temperature_avg: Optional[float] = None

    # Humidity (%)
    humidity_min: Optional[float] = None
    humidity_max: Optional[float] = None
    humidity_avg: Optional[float] = None

    # VPD (kPa)
    vpd_min: Optional[float] = None
    vpd_max: Optional[float] = None
    vpd_avg: Optional[float] = None

    # Pressure (hPa)
    pressure_min: Optional[float] = None
    pressure_max: Optional[float] = None
    pressure_avg: Optional[float] = None

    # Altitude (m)
    altitude_min: Optional[float] = None
    altitude_max: Optional[float] = None
    altitude_avg: Optional[float] = None

    # Gas Resistance (Ohms)
    gas_resistance_min: Optional[float] = None
    gas_resistance_max: Optional[float] = None
    gas_resistance_avg: Optional[float] = None

    # Air Quality Score (0-100)
    air_quality_score_min: Optional[int] = None
    air_quality_score_max: Optional[int] = None
    air_quality_score_avg: Optional[float] = None

    # Light - Lux
    lux_min: Optional[float] = None
    lux_max: Optional[float] = None
    lux_avg: Optional[float] = None

    # Light - PPFD (µmol/m²/s)
    ppfd_min: Optional[float] = None
    ppfd_max: Optional[float] = None
    ppfd_avg: Optional[float] = None

    # Light detection (true if lux exceeded threshold at any point)
    light_detected: Optional[bool] = None


class HydroDailyReport(BaseModel):
    """
    Daily aggregated report from hydro controller.
    Device calculates min/max/avg throughout the day and posts once daily.
    """
    report_date: str  # Date in YYYY-MM-DD format
    readings_count: int  # Number of readings aggregated

    # pH
    ph_min: Optional[float] = None
    ph_max: Optional[float] = None
    ph_avg: Optional[float] = None

    # EC (mS/cm)
    ec_min: Optional[float] = None
    ec_max: Optional[float] = None
    ec_avg: Optional[float] = None

    # Water Level (%)
    water_level_min: Optional[float] = None
    water_level_max: Optional[float] = None
    water_level_avg: Optional[float] = None

    # Water Temperature (°C or °F)
    water_temp_min: Optional[float] = None
    water_temp_max: Optional[float] = None
    water_temp_avg: Optional[float] = None

    # Air Temperature (°C or °F)
    air_temp_min: Optional[float] = None
    air_temp_max: Optional[float] = None
    air_temp_avg: Optional[float] = None

    # Dosing events that occurred during the day
    dosing_events: List[DosingEventSchema] = []
