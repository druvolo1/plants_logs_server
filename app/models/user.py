# app/models/user.py
"""
User and OAuth account models.
"""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    id = Column(Integer, primary_key=True)
    oauth_name = Column(String(255), nullable=False)
    access_token = Column(String(1024), nullable=False)
    expires_at = Column(Integer, nullable=True)
    refresh_token = Column(String(1024), nullable=True)
    account_id = Column(String(255), nullable=False, index=True)
    account_email = Column(String(255), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="oauth_accounts")


class LoginHistory(Base):
    __tablename__ = "login_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    login_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    ip_address = Column(String(45), nullable=True)  # IPv6 max length is 45
    user_agent = Column(String(500), nullable=True)
    user = relationship("User", back_populates="login_history")


class User(Base):
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
    dashboard_preferences = Column(Text, nullable=True)  # JSON string for dashboard settings (device order, etc.)
    created_at = Column(DateTime, nullable=True, default=datetime.utcnow)  # User creation timestamp (NULL for users created before tracking)
    last_login = Column(DateTime, nullable=True)  # Last login timestamp
    login_count = Column(Integer, nullable=False, default=0)  # Total login count
    oauth_accounts = relationship("OAuthAccount", back_populates="user", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")
    login_history = relationship("LoginHistory", back_populates="user", cascade="all, delete-orphan", order_by="LoginHistory.login_at.desc()")
    grower_profile = relationship("GrowerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
