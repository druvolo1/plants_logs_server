# app/routers/__init__.py
"""
API route handlers organized by domain.
"""
from .templates import router as templates_router

__all__ = [
    "templates_router",
]
