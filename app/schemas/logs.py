"""Log-related Pydantic schemas."""
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class LogEntryCreate(BaseModel):
    """Log entry creation schema."""
    event_type: str
    sensor_name: Optional[str] = None
    value: Optional[float] = None
    dose_type: Optional[str] = None
    dose_amount_ml: Optional[float] = None
    timestamp: str


class LogEntryRead(BaseModel):
    """Log entry read schema."""
    id: int
    event_type: str
    sensor_name: Optional[str]
    value: Optional[float]
    dose_type: Optional[str]
    dose_amount_ml: Optional[float]
    timestamp: datetime


class EnvironmentDataCreate(BaseModel):
    """Environment data creation schema."""
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
    timestamp: str


class EnvironmentLogRead(BaseModel):
    """Environment log read schema."""
    id: int
    device_id: int
    location_id: Optional[int]
    co2: Optional[int]
    temperature: Optional[float]
    humidity: Optional[float]
    vpd: Optional[float]
    pressure: Optional[float]
    altitude: Optional[float]
    gas_resistance: Optional[float]
    air_quality_score: Optional[int]
    lux: Optional[float]
    ppfd: Optional[float]
    timestamp: datetime
    created_at: datetime
