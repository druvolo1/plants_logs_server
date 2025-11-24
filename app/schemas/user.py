# app/schemas/user.py
"""
User-related Pydantic schemas.
"""
from typing import Optional
from pydantic import BaseModel, EmailStr
from fastapi_users import schemas


class UserRead(schemas.BaseUser[int]):
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserCreate(schemas.BaseUserCreate):
    password: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: Optional[bool] = False  # Default to pending approval
    is_superuser: Optional[bool] = False
    is_verified: Optional[bool] = False
    is_suspended: Optional[bool] = False  # Default to not suspended


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    is_suspended: Optional[bool] = None


class UserLogin(BaseModel):
    username: str
    password: str


class PasswordReset(BaseModel):
    password: str
