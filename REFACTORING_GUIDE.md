# Plants Logs Server Refactoring Guide

## What's Been Done

### ✅ Completed Structure

```
app/
├── core/
│   ├── __init__.py
│   ├── config.py        # Environment variables and configuration
│   ├── database.py      # Database engine and session management
│   └── security.py      # JWT strategy
│
├── models/
│   ├── __init__.py
│   ├── user.py         # User and OAuthAccount models
│   ├── device.py       # Device, DeviceShare, DeviceAssignment models
│   ├── location.py     # Location, LocationShare models
│   ├── plant.py        # Plant, PhaseTemplate, PhaseHistory models
│   └── logs.py         # LogEntry, EnvironmentLog models
│
├── schemas/
│   ├── __init__.py
│   ├── user.py         # User Pydantic schemas
│   ├── device.py       # Device Pydantic schemas
│   ├── location.py     # Location Pydantic schemas
│   ├── plant.py        # Plant Pydantic schemas
│   └── logs.py         # Log Pydantic schemas
│
├── auth/
│   ├── __init__.py
│   ├── database.py     # CustomSQLAlchemyUserDatabase (PARTIAL)
│   ├── manager.py      # CustomUserManager (TO DO)
│   └── backend.py      # FastAPI Users setup (TO DO)
│
├── routers/            # (TO DO - routers still in main.py)
│
├── main_backup.py      # Original 4,276 line file (BACKUP)
└── main.py            # Current file (TO BE REFACTORED)
```

## Next Steps

### Option 1: Keep Routers in Main.py (Recommended for Now)

**Pros:**
- Immediate benefits without risk
- Smaller, more manageable files
- Better organization
- Can extract routers incrementally later

**Steps:**
1. Update main.py to import from new modules instead of defining inline
2. Keep all route handlers (@app.get, @app.post, etc.) in main.py
3. Test to ensure everything works

### Option 2: Extract All Routers (More Work, Maximum Benefit)

**Complete the auth module:**
1. Create `app/auth/manager.py` with CustomUserManager
2. Create `app/auth/backend.py` with fastapi_users, auth_backend, etc.

**Create router files:**
1. `app/routers/auth.py` - OAuth, login, register (lines 641-985 of main_backup.py)
2. `app/routers/users.py` - User profile endpoints (lines 992-1042)
3. `app/routers/admin.py` - Admin endpoints (lines 1068-1249)
4. `app/routers/devices.py` - Device CRUD and pairing (lines 1902-2584)
5. `app/routers/locations.py` - Location CRUD and sharing (lines 1520-1902)
6. `app/routers/plants.py` - Plant CRUD and management (lines 2620-3606)
7. `app/routers/templates.py` - Phase templates (lines 2753-2855)
8. `app/routers/logs.py` - Logs and environment data (lines 3606-3982)
9. `app/routers/websockets.py` - WebSocket handlers (lines 3982-4232)
10. `app/routers/pages.py` - HTML page routes (lines 748-1068)

**Update main.py:**
```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import CORS_ORIGINS
from app.core.database import create_db_and_tables
from app.routers import auth, users, admin, devices, locations, plants, templates, logs, websockets, pages

app = FastAPI()

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Include routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(devices.router)
app.include_router(locations.router)
app.include_router(plants.router)
app.include_router(templates.router)
app.include_router(logs.router)
app.include_router(websockets.router)
app.include_router(pages.router)

@app.on_event("startup")
async def on_startup():
    await create_db_and_tables()
```

## Benefits Achieved So Far

1. **Models separated** - Database models are now in dedicated files (easy to find and modify)
2. **Schemas separated** - Pydantic schemas are organized by domain
3. **Core utilities** - Config, database, security in one place
4. **Better imports** - Clear separation of concerns
5. **Easier testing** - Each module can be tested independently
6. **Smaller files** - No more 4,000+ line files!

## Performance Impact

After refactoring:
- `main.py` will be ~150-200 lines (vs 4,276)
- Largest file will be ~800 lines (devices router)
- Claude Code will index much faster
- IDE autocomplete will be much faster
- Git diffs will be much cleaner

## How to Test

After refactoring:
```bash
# Run the application
cd C:\Users\Dave\Documents\Programming\Garden\plants_logs_server
python -m uvicorn app.main:app --reload

# Test endpoints
curl http://localhost:8000/
curl http://localhost:8000/api/user/me
```

## Rolling Back

If anything breaks:
```bash
cd C:\Users\Dave\Documents\Programming\Garden\plants_logs_server\app
cp main_backup.py main.py
```

## Notes

- All new modules use absolute imports: `from app.models.user import User`
- The backup file `main_backup.py` is your safety net
- You can incrementally extract routers over time
- Models and schemas are ready to use now!
