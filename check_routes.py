#!/usr/bin/env python3
"""Check registered routes in the FastAPI app"""
import sys
sys.path.insert(0, '.')

from app.main import app

print("Routes containing '/logs' or '/api/devices':")
print("=" * 80)
for route in app.routes:
    if hasattr(route, 'path'):
        if '/logs' in route.path or '/api/devices' in route.path:
            methods = list(route.methods) if hasattr(route, 'methods') else []
            print(f"{methods[0] if methods else 'GET':6} {route.path:50} {route.name}")
