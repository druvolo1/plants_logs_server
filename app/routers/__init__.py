# app/routers/__init__.py
"""
API route handlers organized by domain.
"""
from .templates import router as templates_router
from .locations import router as locations_router
from .admin import router as admin_router
from .logs import router as logs_router

__all__ = [
    "templates_router",
    "locations_router",
    "admin_router",
    "logs_router",
]
