# app/routers/__init__.py
"""
API route handlers organized by domain.
"""
from .templates import router as templates_router
from .locations import router as locations_router
from .admin import router as admin_router
from .logs import router as logs_router
from .plants import router as plants_router, api_router as plants_api_router

__all__ = [
    "templates_router",
    "locations_router",
    "admin_router",
    "logs_router",
    "plants_router",
    "plants_api_router",
]
