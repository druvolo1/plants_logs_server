"""Location-related Pydantic schemas."""
from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class LocationCreate(BaseModel):
    """Location creation schema."""
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None


class LocationUpdate(BaseModel):
    """Location update schema."""
    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None


class LocationRead(BaseModel):
    """Location read schema."""
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
    """Location share creation schema."""
    permission_level: str
    expires_in_days: Optional[int] = 7


class LocationShareRead(BaseModel):
    """Location share read schema."""
    id: int
    location_id: int
    share_code: str
    permission_level: str
    created_at: datetime
    expires_at: datetime
    accepted_at: Optional[datetime]
    is_active: bool
    shared_with_email: Optional[str]
