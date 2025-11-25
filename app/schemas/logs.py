# app/schemas/logs.py
"""
Log-related Pydantic schemas.
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


from typing import Union, Any
from pydantic import field_validator

class LogEntryCreate(BaseModel):
    event_type: str  # 'sensor' or 'dosing'
    sensor_name: Optional[str] = None
    value: Optional[float] = None
    dose_type: Optional[str] = None
    dose_amount_ml: Optional[float] = None
    timestamp: str  # ISO format datetime string

    @field_validator('value', mode='before')
    @classmethod
    def parse_value(cls, v):
        """Handle 'N/A' or other non-numeric values gracefully"""
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            # Handle 'N/A', 'null', empty strings, etc.
            if v.lower() in ('n/a', 'na', 'null', 'none', ''):
                return None
            try:
                return float(v)
            except ValueError:
                return None
        return None


class LogEntryRead(BaseModel):
    id: int
    event_type: str
    sensor_name: Optional[str]
    value: Optional[float]
    dose_type: Optional[str]
    dose_amount_ml: Optional[float]
    timestamp: datetime


class EnvironmentDataCreate(BaseModel):
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


class EnvironmentLogRead(BaseModel):
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
