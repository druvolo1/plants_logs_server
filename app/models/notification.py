# app/models/notification.py
"""
Notification model for device alerts and notifications.
"""
from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Enum, Text, Index
from sqlalchemy.sql import func
from datetime import datetime
import enum
from .base import Base


class NotificationSeverity(str, enum.Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class NotificationStatus(str, enum.Enum):
    """Alert status"""
    ACTIVE = "active"
    SELF_CLEARED = "self_cleared"
    USER_CLEARED = "user_cleared"


class Notification(Base):
    """
    Notifications/alerts from devices.
    Tracks device alerts with deduplication by (device_id, alert_type).
    """
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(100), nullable=False, index=True)  # Matches devices.device_id
    alert_type = Column(String(100), nullable=False)  # e.g., "PH_OUT_OF_RANGE"
    alert_type_id = Column(Integer, nullable=False)  # Numeric enum value from device
    severity = Column(Enum(NotificationSeverity), nullable=False)
    status = Column(Enum(NotificationStatus), nullable=False, default=NotificationStatus.ACTIVE)
    source = Column(String(200), nullable=False)  # e.g., "pH Probe"
    message = Column(Text, nullable=False)  # Detailed alert message
    first_occurrence = Column(BigInteger, nullable=False)  # millis timestamp from device
    last_occurrence = Column(BigInteger, nullable=True)  # millis timestamp from device
    cleared_at = Column(BigInteger, nullable=True)  # millis timestamp when cleared
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index('unique_device_alert', 'device_id', 'alert_type', unique=True),
        Index('idx_status_cleared', 'status', 'cleared_at'),
        Index('idx_device_status', 'device_id', 'status'),
        Index('idx_severity', 'severity'),
        Index('idx_created_at', 'created_at'),
    )
