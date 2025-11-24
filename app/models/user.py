"""User and OAuth account models."""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class OAuthAccount(Base):
    """OAuth account model for third-party authentication."""
    __tablename__ = "oauth_accounts"

    id = Column(Integer, primary_key=True)
    oauth_name = Column(String(255), nullable=False)
    access_token = Column(String(1024), nullable=False)
    expires_at = Column(Integer, nullable=True)
    refresh_token = Column(String(1024), nullable=True)
    account_id = Column(String(255), nullable=False, index=True)
    account_email = Column(String(255), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Relationships
    user = relationship("User", back_populates="oauth_accounts")


class User(Base):
    """User model."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True)
    hashed_password = Column(String(1024), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=False)  # Changed default to False for pending approval
    is_superuser = Column(Boolean, default=False)  # For admin
    is_verified = Column(Boolean, default=False)
    is_suspended = Column(Boolean, default=False)  # Added for suspended users
    dashboard_preferences = Column(Text, nullable=True)  # JSON string for dashboard settings

    # Relationships
    oauth_accounts = relationship("OAuthAccount", back_populates="user", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")
