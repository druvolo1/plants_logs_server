# app/schemas/notification.py
"""
Notification-related Pydantic schemas.
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from app.models.notification import NotificationSeverity, NotificationStatus


class NotificationBase(BaseModel):
    """Base notification schema"""
    device_id: str
    alert_type: str
    alert_type_id: int
    severity: NotificationSeverity
    status: NotificationStatus
    source: str
    message: str
    first_occurrence: int  # millis timestamp
    last_occurrence: Optional[int] = None  # millis timestamp
    cleared_at: Optional[int] = None  # millis timestamp


class NotificationCreate(NotificationBase):
    """Schema for creating a new notification (from device)"""
    pass


class NotificationUpdate(BaseModel):
    """Schema for updating a notification"""
    status: Optional[NotificationStatus] = None
    last_occurrence: Optional[int] = None
    cleared_at: Optional[int] = None
    message: Optional[str] = None


class NotificationInDB(NotificationBase):
    """Notification as stored in database"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NotificationRead(NotificationInDB):
    """Notification response schema"""
    pass


class NotificationSummary(BaseModel):
    """Summary of notification counts"""
    total: int
    active: int
    warnings: int
    critical: int
    info: int


class NotificationClearRequest(BaseModel):
    """Request to clear notification(s)"""
    notification_ids: Optional[list[int]] = None  # Specific IDs to clear, or None for all
