# app/main.py - Full app with FastAPI-Users (async SQLAlchemy)
from fastapi import FastAPI, Depends, HTTPException, Request, Form, Response, status, Body, Header
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean, select, ForeignKey, DateTime, Float, Text, func, or_
from sqlalchemy.orm import relationship, selectinload, Session
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from typing import List, Optional, Generator, Any, Dict
from fastapi_users import FastAPIUsers, BaseUserManager, IntegerIDMixin
from fastapi_users.authentication import CookieTransport, AuthenticationBackend, JWTStrategy
from fastapi_users.authentication.strategy.db import AccessTokenDatabase, DatabaseStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi.security import OAuth2AuthorizationCodeBearer, OAuth2PasswordRequestForm
from httpx_oauth.clients.google import GoogleOAuth2
from fastapi_users import schemas, exceptions
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
import os
import secrets  # Added for API key
import jwt  # Added for WebSocket JWT decoding
import asyncio
import time

# Added for WS
from fastapi import WebSocket, Query
from starlette.websockets import WebSocketDisconnect
from starlette.responses import RedirectResponse
from collections import defaultdict
import json
from sqlalchemy import update, delete, and_, or_

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
print("Loaded DATABASE_URL from .env:", DATABASE_URL)  # Debug print
DATABASE_URL = DATABASE_URL.replace("mariadb+mariadbconnector", "mariadb+aiomysql") if DATABASE_URL else None
print("Modified DATABASE_URL for async:", DATABASE_URL)  # Debug print
SECRET = os.getenv("SECRET_KEY") or "secret"
SERVER_URL = os.getenv("SERVER_URL")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

engine = create_async_engine(
    DATABASE_URL,
    connect_args={
        "init_command": "SET time_zone='+00:00'"  # Force UTC for all sessions
    }
)

class AsyncSessionGreenlet(AsyncSession):
    def __init__(self, *args, **kwargs):
        super().__init__(sync_session_class=Session, *args, **kwargs)

async_session_maker = async_sessionmaker(engine, class_=AsyncSessionGreenlet, expire_on_commit=False)

# Import models from models package
from app.models import (
    Base,
    User,
    OAuthAccount,
    Device,
    DeviceShare,
    Location,
    LocationShare,
    Plant,
    PhaseTemplate,
    PhaseHistory,
    DeviceAssignment,
    PlantDailyLog,
    PlantReport,
    Notification,
    NotificationStatus,
)

async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Import Pydantic schemas from schemas package
from app.schemas import (
    UserRead,
    UserCreate,
    UserUpdate,
    UserLogin,
    PasswordReset,
    DeviceCreate,
    DeviceUpdate,
    DeviceRead,
    DeviceSettingsUpdate,
    DeviceSettingsResponse,
    DevicePairRequest,
    DevicePairResponse,
    AssignedPlantInfo,
    ShareCreate,
    ShareAccept,
    ShareUpdate,
    ShareRead,
    LocationCreate,
    LocationUpdate,
    LocationRead,
    LocationShareCreate,
    LocationShareRead,
    PlantCreate,
    PlantCreateNew,
    PlantRead,
    PlantFinish,
    PlantYieldUpdate,
    PhaseTemplateCreate,
    PhaseTemplateRead,
    DeviceAssignmentCreate,
    AssignedDeviceInfo,
    HydroReadingCreate,
    EnvironmentDataCreate,
    PlantDailyLogRead,
)

class CustomSQLAlchemyUserDatabase(SQLAlchemyUserDatabase[User, int]):
    async def add_oauth_account(
        self, user: User, create_dict: Dict[str, Any]
    ) -> User:
        # Preload oauth_accounts to avoid lazy loading
        stmt = (
            select(self.user_table)
            .options(selectinload(self.user_table.oauth_accounts))
            .where(self.user_table.id == user.id)
        )
        result = await self.session.execute(stmt)
        user = result.scalars().one_or_none()
        if user is None:
            raise ValueError("User not found")

        if self.oauth_account_table is None:
            raise ValueError("No OAuth account table configured.")

        oauth_account = self.oauth_account_table(**create_dict)
        self.session.add(oauth_account)
        user.oauth_accounts.append(oauth_account)
        await self.session.commit()
        return user

class CustomUserManager(IntegerIDMixin, BaseUserManager[User, int]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def create(self, user_create, safe: bool = False, request = None):
        """Override create to ensure is_suspended is set"""
        # Call parent create
        user = await super().create(user_create, safe=safe, request=request)

        # Explicitly ensure is_suspended is False if not already set
        if not hasattr(user, 'is_suspended') or user.is_suspended is None:
            await self.user_db.update(user, {"is_suspended": False})
            await self.user_db.session.refresh(user)
            print(f"Explicitly set is_suspended=False for user {user.email}")

        return user

    async def on_after_register(self, user: User, request: None = None):
        print(f"User {user.email} (id={user.id}) has registered and is pending approval.")

    async def authenticate(self, credentials: OAuth2PasswordRequestForm) -> Optional[User]:
        """
        Override authenticate to check if user is active (not pending)
        """
        try:
            user = await self.get_by_email(credentials.username)
        except exceptions.UserNotExists:
            # Run the hasher to mitigate timing attack
            self.password_helper.hash(credentials.password)
            return None

        verified, updated_password_hash = self.password_helper.verify_and_update(
            credentials.password, user.hashed_password
        )
        if not verified:
            return None

        # Check if user is suspended (handle None as False)
        is_suspended = getattr(user, 'is_suspended', None)
        is_active = user.is_active

        # Normalize is_suspended to boolean (handle None, 0, 1, True, False)
        if is_suspended is None or is_suspended is False or is_suspended == 0:
            is_suspended = False
        else:
            is_suspended = True

        if is_suspended:
            raise HTTPException(
                status_code=403,
                detail="SUSPENDED"
            )

        # Check if user is pending approval
        if not is_active:
            raise HTTPException(
                status_code=403,
                detail="PENDING_APPROVAL"
            )
        
        # Update password hash to a more robust one if needed
        if updated_password_hash is not None:
            await self.user_db.update(user, {"hashed_password": updated_password_hash})

        return user

    async def oauth_callback(
        self,
        oauth_name: str,
        access_token: str,
        account_id: str,
        account_email: str,
        expires_at: Optional[int] = None,
        refresh_token: Optional[str] = None,
        request: Optional[Request] = None,
        *,
        associate_by_email: bool = False,
        is_verified_by_default: bool = False,
    ) -> User:
        print(f"OAuth callback START for {account_email}")
        try:
            oauth_account_dict = {
                "oauth_name": oauth_name,
                "access_token": access_token,
                "account_id": account_id,
                "account_email": account_email,
                "expires_at": expires_at,
                "refresh_token": refresh_token,
            }

            try:
                user = await self.get_by_oauth_account(oauth_name, account_id)
                print(f"Existing OAuth user found: {account_email}")
                # User already has this OAuth account linked, just return them
            except exceptions.UserNotExists:
                user = None
                print(f"No existing OAuth user for {account_email}")

                # Try to find user by email and link OAuth account
                if associate_by_email:
                    try:
                        user = await self.get_by_email(account_email)
                        if user:
                            # Eagerly load oauth_accounts to avoid lazy load in the check
                            stmt = (
                                select(User)
                                .options(selectinload(User.oauth_accounts))
                                .where(User.email == account_email)
                            )
                            result = await self.user_db.session.execute(stmt)
                            user = result.scalars().one_or_none()

                            # Check if user already has this OAuth account
                            has_oauth = False
                            for existing_oauth_account in user.oauth_accounts:
                                if existing_oauth_account.oauth_name == oauth_name:
                                    has_oauth = True
                                    break

                            # Only add OAuth account if not already linked
                            if not has_oauth:
                                user = await self.user_db.add_oauth_account(user, oauth_account_dict)
                                print(f"OAuth account linked to existing user {account_email}")
                    except exceptions.UserNotExists:
                        pass

            if not user:
                # Google OAuth users also require approval (is_active=False)
                # Generate a random secure password (OAuth users won't use it)
                random_password = secrets.token_urlsafe(32)
                user_create = UserCreate(
                    email=account_email,
                    password=random_password,  # Random password for OAuth users (not used)
                    is_verified=is_verified_by_default,
                    is_active=False,  # Require approval for OAuth users
                    is_suspended=False  # Explicitly set not suspended
                )
                user = await self.create(user_create)

                # Refresh user from database to get all fields
                await self.user_db.session.refresh(user)

                # Debug: Check what was actually saved
                print(f"OAuth user created: email={user.email}, is_active={user.is_active}, is_suspended={getattr(user, 'is_suspended', 'MISSING')}")

                try:
                    user = await self.user_db.add_oauth_account(user, oauth_account_dict)
                    print(f"OAuth account successfully linked for {user.email}")
                except Exception as e:
                    print(f"ERROR linking OAuth account for {user.email}: {e}")
                    raise

            # Note: We don't check for suspended/pending here because OAuth callback
            # should always succeed and set the cookie. The checks happen when the user
            # tries to access protected routes via the current_user dependency.
            print(f"OAuth callback complete for {user.email}, is_active={user.is_active}, is_suspended={getattr(user, 'is_suspended', None)}")
            return user
        except Exception as e:
            print(f"ERROR in OAuth callback for {account_email}: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise

async def get_db():
    async with async_session_maker() as session:
        yield session

async def get_user_db(session: AsyncSession = Depends(get_db)):
    yield CustomSQLAlchemyUserDatabase(session, User, oauth_account_table=OAuthAccount)

async def get_user_manager(user_db: CustomSQLAlchemyUserDatabase = Depends(get_user_db)):
    yield CustomUserManager(user_db)

cookie_transport = CookieTransport(cookie_name="auth_cookie", cookie_max_age=3600)

def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)

auth_backend = AuthenticationBackend(
    name="jwt",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

google_oauth_client = GoogleOAuth2(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)

fastapi_users = FastAPIUsers[User, int](
    get_user_manager,
    [auth_backend],
)

_base_current_user = fastapi_users.current_user(active=False)  # Don't check active here
_base_current_admin = fastapi_users.current_user(active=False, superuser=True)  # Don't check active here

# Custom dependency to check for suspended and pending users
async def current_user(user: User = Depends(_base_current_user)) -> User:
    """Check if user is suspended or pending before allowing access"""
    # Check if user is suspended (handle None as False)
    is_suspended = getattr(user, 'is_suspended', None)
    is_active = user.is_active

    # Debug logging
    print(f"current_user check for {user.email}: is_suspended={is_suspended}, is_active={is_active}")

    # Normalize is_suspended to boolean (handle None, 0, 1, True, False)
    if is_suspended is None or is_suspended is False or is_suspended == 0:
        is_suspended = False
    else:
        is_suspended = True

    if is_suspended:
        print(f"User {user.email} is SUSPENDED - showing suspended page")
        raise HTTPException(
            status_code=403,
            detail="SUSPENDED"
        )
    # Check if user is pending approval
    if not is_active:
        print(f"User {user.email} is PENDING - showing pending approval page")
        raise HTTPException(
            status_code=403,
            detail="PENDING_APPROVAL"
        )
    return user

async def current_admin(user: User = Depends(_base_current_admin)) -> User:
    """Check if admin is suspended or pending before allowing access"""
    # Check if user is suspended (handle None as False)
    is_suspended = getattr(user, 'is_suspended', None)
    is_active = user.is_active

    # Normalize is_suspended to boolean (handle None, 0, 1, True, False)
    if is_suspended is None or is_suspended is False or is_suspended == 0:
        is_suspended = False
    else:
        is_suspended = True

    if is_suspended:
        raise HTTPException(
            status_code=403,
            detail="SUSPENDED"
        )
    # Check if user is pending approval
    if not is_active:
        raise HTTPException(
            status_code=403,
            detail="PENDING_APPROVAL"
        )
    return user

app = FastAPI()

# Add CORS middleware to allow cross-origin requests from pH dosing systems
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (pH dosing systems can be on any local network)
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Include routers
from app.routers import templates_router, locations_router, admin_router, logs_router, plants_router, plants_api_router, devices_router, devices_api_router, auth_router, auth_api_router, websocket_router, pages_router, firmware_router, notifications_router, social_router
app.include_router(templates_router)
app.include_router(locations_router)
app.include_router(admin_router)
app.include_router(logs_router)
app.include_router(plants_router)
app.include_router(plants_api_router)
app.include_router(devices_router)
app.include_router(devices_api_router)
app.include_router(auth_router)
app.include_router(auth_api_router)
app.include_router(websocket_router)
app.include_router(pages_router)
app.include_router(firmware_router)
app.include_router(notifications_router)
app.include_router(social_router)

# Global exception handler for suspended/pending users
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.detail == "SUSPENDED":
        # Clear auth cookie
        response = templates.TemplateResponse("suspended.html", {"request": request}, status_code=403)
        response.delete_cookie("auth_cookie")
        return response
    elif exc.detail == "PENDING_APPROVAL":
        # Clear auth cookie
        response = templates.TemplateResponse("pending_approval.html", {"request": request}, status_code=403)
        response.delete_cookie("auth_cookie")
        return response
    # Re-raise other HTTP exceptions
    raise exc

# Validation exception handler to debug 422 errors
from fastapi.exceptions import RequestValidationError
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Log the validation errors and request body for debugging
    print(f"[VALIDATION ERROR] URL: {request.url}")
    print(f"[VALIDATION ERROR] Method: {request.method}")
    try:
        body = await request.body()
        body_str = body.decode('utf-8')[:2000]  # Limit to first 2000 chars
        print(f"[VALIDATION ERROR] Body (first 2000 chars): {body_str}")
    except Exception as e:
        print(f"[VALIDATION ERROR] Could not read body: {e}")
    print(f"[VALIDATION ERROR] Errors: {exc.errors()}")

    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

# Auth routes moved to app/routers/auth.py
# Page routes moved to app/routers/pages.py
# WebSocket endpoints moved to app/routers/websocket.py

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        # Special handling for pairing flow - redirect to login with return URL
        if request.url.path == "/pair-device-auth":
            device_id = request.query_params.get('device_id')
            redirect_url = f"/login?next=/pair-device-auth"
            if device_id:
                redirect_url += f"&device_id={device_id}"
            return RedirectResponse(url=redirect_url, status_code=302)
        return templates.TemplateResponse("unauthorized.html", {"request": request}, status_code=401)
    if exc.status_code == 400 and exc.detail == "LOGIN_BAD_CREDENTIALS":
        return templates.TemplateResponse("suspended.html", {"request": request}, status_code=400)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

async def cleanup_old_notifications_task():
    """
    Background task that periodically cleans up old cleared notifications.
    Runs every hour and removes notifications that have been cleared for more than 24 hours.
    """
    while True:
        try:
            # Wait 1 hour between cleanup runs
            await asyncio.sleep(3600)

            print("[NOTIFICATION CLEANUP] Starting cleanup of old notifications...")

            # Calculate cutoff time (24 hours ago in millis)
            cutoff_millis = int((time.time() - 24 * 60 * 60) * 1000)

            async with async_session_maker() as session:
                # Delete cleared notifications older than 24 hours
                stmt = delete(Notification).where(
                    and_(
                        or_(
                            Notification.status == NotificationStatus.SELF_CLEARED,
                            Notification.status == NotificationStatus.USER_CLEARED
                        ),
                        Notification.cleared_at < cutoff_millis
                    )
                )

                result = await session.execute(stmt)
                await session.commit()

                deleted_count = result.rowcount
                print(f"[NOTIFICATION CLEANUP] Deleted {deleted_count} old notification(s)")

        except Exception as e:
            print(f"[NOTIFICATION CLEANUP] ERROR during cleanup: {e}")
            import traceback
            traceback.print_exc()


@app.on_event("startup")
async def on_startup():
    # Initialize database schema (add missing columns if needed)
    from app.init_database import init_database
    await init_database()

    await create_db_and_tables()
    print("Tables created or already exist.")
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == os.getenv("ADMIN_USERNAME")))
        admin = result.scalars().first()
        if not admin:
            print("No admin found, creating one with password: " + os.getenv("ADMIN_PASSWORD"))
            admin_create = UserCreate(
                email=os.getenv("ADMIN_USERNAME"),
                password=os.getenv("ADMIN_PASSWORD"),
                is_superuser=True,
                is_active=True,
                is_verified=True
            )
            user_db = CustomSQLAlchemyUserDatabase(session, User, oauth_account_table=OAuthAccount)
            manager = CustomUserManager(user_db)
            await manager.create(admin_create)
            await session.commit()
            print("Admin created.")
        else:
            print("Admin already exists.")

    # Start background task for notification cleanup
    asyncio.create_task(cleanup_old_notifications_task())
    print("[NOTIFICATION CLEANUP] Background cleanup task started")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=9000, reload=True)