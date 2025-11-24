# app/schemas/location.py
"""
Location-related Pydantic schemas.
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class LocationCreate(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None


class LocationRead(BaseModel):
    id: int
    name: str
    description: Optional[str]
    parent_id: Optional[int]
    user_id: int
    created_at: datetime
    updated_at: datetime
    is_owner: bool = True
    permission_level: Optional[str] = None
    shared_by_email: Optional[str] = None


class LocationShareCreate(BaseModel):
    permission_level: str  # 'viewer' or 'controller'
    expires_in_days: Optional[int] = 7  # None for never expire


class LocationShareRead(BaseModel):
    id: int
    location_id: int
    share_code: str
    permission_level: str
    created_at: datetime
    expires_at: datetime
    accepted_at: Optional[datetime]
    is_active: bool
    shared_with_email: Optional[str]
