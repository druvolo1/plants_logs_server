"""Authentication module."""
from .database import CustomSQLAlchemyUserDatabase, get_user_db
from .manager import CustomUserManager, get_user_manager
from .backend import fastapi_users, auth_backend, current_user, current_admin, google_oauth_client

__all__ = [
    "CustomSQLAlchemyUserDatabase",
    "get_user_db",
    "CustomUserManager",
    "get_user_manager",
    "fastapi_users",
    "auth_backend",
    "current_user",
    "current_admin",
    "google_oauth_client",
]
