# app/routers/__init__.py
"""
API route handlers organized by domain.
"""
from .templates import router as templates_router
from .locations import router as locations_router
from .admin import router as admin_router
from .logs import router as logs_router
from .plants import router as plants_router, api_router as plants_api_router
from .devices import router as devices_router, api_router as devices_api_router
from .auth import router as auth_router, api_router as auth_api_router
from .websocket import router as websocket_router, device_connections, user_connections
from .pages import router as pages_router, pending_pairings
from .firmware import router as firmware_router

__all__ = [
    "templates_router",
    "locations_router",
    "admin_router",
    "logs_router",
    "plants_router",
    "plants_api_router",
    "devices_router",
    "devices_api_router",
    "auth_router",
    "auth_api_router",
    "websocket_router",
    "device_connections",
    "user_connections",
    "pages_router",
    "pending_pairings",
    "firmware_router",
]
