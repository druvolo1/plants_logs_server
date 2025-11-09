# app/main.py - Full app with FastAPI-Users (async SQLAlchemy)
from fastapi import FastAPI, Depends, HTTPException, Request, Form, Response, status, Body
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean, select, ForeignKey, DateTime, Float, Text, func
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

# Added for WS
from fastapi import WebSocket, Query
from starlette.websockets import WebSocketDisconnect
from collections import defaultdict
import json
from sqlalchemy import update

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
print("Loaded DATABASE_URL from .env:", DATABASE_URL)  # Debug print
DATABASE_URL = DATABASE_URL.replace("mariadb+mariadbconnector", "mariadb+aiomysql") if DATABASE_URL else None
print("Modified DATABASE_URL for async:", DATABASE_URL)  # Debug print
SECRET = os.getenv("SECRET_KEY") or "secret"
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI") or "http://garden.ruvolo.loseyourip.com/auth/google/callback"

engine = create_async_engine(DATABASE_URL)

class AsyncSessionGreenlet(AsyncSession):
    def __init__(self, *args, **kwargs):
        super().__init__(sync_session_class=Session, *args, **kwargs)

async_session_maker = async_sessionmaker(engine, class_=AsyncSessionGreenlet, expire_on_commit=False)
Base = declarative_base()

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

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True)
    hashed_password = Column(String(1024), nullable=True)
    first_name = Column(String(255), nullable=True)  # Added
    last_name = Column(String(255), nullable=True)   # Added
    is_active = Column(Boolean, default=False)  # Changed default to False for pending approval
    is_superuser = Column(Boolean, default=False)  # For admin
    is_verified = Column(Boolean, default=False)
    is_suspended = Column(Boolean, default=False)  # Added for suspended users
    dashboard_preferences = Column(Text, nullable=True)  # JSON string for dashboard settings (device order, etc.)
    oauth_accounts = relationship("OAuthAccount", back_populates="user", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="user", cascade="all, delete-orphan")  # Added backref

# Added Device model
class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(36), unique=True, index=True)
    api_key = Column(String(64))
    name = Column(String(255), nullable=True)
    is_online = Column(Boolean, default=False)
    device_type = Column(String(50), nullable=True, default='feeding_system')  # 'feeding_system', 'curing_monitor', 'environmental'
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="devices")
    plants = relationship("Plant", foreign_keys="Plant.device_id", cascade="all, delete-orphan", passive_deletes=False)
    device_assignments = relationship("DeviceAssignment", back_populates="device", cascade="all, delete-orphan")

# Device Sharing model
class DeviceShare(Base):
    __tablename__ = "device_shares"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    shared_with_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL until accepted
    share_code = Column(String(12), unique=True, index=True, nullable=False)
    permission_level = Column(String(20), nullable=False)  # 'viewer' or 'controller'
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    device = relationship("Device", foreign_keys=[device_id])
    owner = relationship("User", foreign_keys=[owner_user_id])
    shared_with = relationship("User", foreign_keys=[shared_with_user_id])

# Device Assignment model - tracks which device is monitoring which plant and during which phase
class DeviceAssignment(Base):
    __tablename__ = "device_assignments"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    phase = Column(String(50), nullable=False)  # 'feeding', 'curing', etc.
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    removed_at = Column(DateTime, nullable=True)  # NULL if still assigned

    # Relationships
    plant = relationship("Plant", back_populates="device_assignments")
    device = relationship("Device", back_populates="device_assignments")

# Plant model
class Plant(Base):
    __tablename__ = "plants"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(String(64), unique=True, index=True, nullable=False)  # Timestamp-based unique ID
    name = Column(String(255), nullable=False)  # Strain name
    system_id = Column(String(255), nullable=True)  # e.g., "Zone1" - legacy field, use device_assignments for new plants
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)  # Made nullable - legacy field for backward compatibility
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    yield_grams = Column(Float, nullable=True)  # Added after harvest
    display_order = Column(Integer, nullable=True, default=0)  # For user-defined ordering

    # New lifecycle fields
    status = Column(String(50), nullable=False, default='created')  # 'created', 'feeding', 'harvested', 'curing', 'finished'
    current_phase = Column(String(50), nullable=True)  # Current phase name, e.g., 'feeding', 'curing'
    harvest_date = Column(DateTime, nullable=True)  # When plant was harvested from feeding
    cure_start_date = Column(DateTime, nullable=True)  # When curing phase started
    cure_end_date = Column(DateTime, nullable=True)  # When curing phase completed

    # Relationships
    device = relationship("Device", foreign_keys=[device_id], back_populates="plants")
    user = relationship("User", foreign_keys=[user_id])
    logs = relationship("LogEntry", back_populates="plant", cascade="all, delete-orphan")
    device_assignments = relationship("DeviceAssignment", back_populates="plant", cascade="all, delete-orphan")

# Log Entry model
class LogEntry(Base):
    __tablename__ = "log_entries"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    event_type = Column(String(20), nullable=False)  # 'sensor' or 'dosing'
    sensor_name = Column(String(50), nullable=True)  # e.g., 'ph', 'ec', 'humidity', 'temperature'
    value = Column(Float, nullable=True)  # pH reading, humidity %, temp, etc.
    dose_type = Column(String(10), nullable=True)  # 'up' or 'down'
    dose_amount_ml = Column(Float, nullable=True)  # Dose amount
    timestamp = Column(DateTime, nullable=False, index=True)
    phase = Column(String(50), nullable=True)  # 'feeding', 'curing', etc. - which phase this log is from

    # Relationships
    plant = relationship("Plant", back_populates="logs")

async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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

# Auth routes - We have custom registration, so don't include the register router
# app.include_router(
#     fastapi_users.get_register_router(UserRead, UserCreate),
#     prefix="/auth",
#     tags=["auth"],
# )

# OAuth router - use custom route to handle pending users
# app.include_router(
#     fastapi_users.get_oauth_router(google_oauth_client, auth_backend, SECRET, associate_by_email=True),
#     prefix="/auth/google",
#     tags=["auth"],
# )

# Custom OAuth routes to handle pending user flow
@app.get("/auth/google/authorize", response_model=dict)
async def google_authorize_custom(request: Request):
    redirect_uri = request.url_for("auth:google.callback")
    auth_url = await google_oauth_client.get_authorization_url(
        str(redirect_uri),
        state=None,
        scope=["openid", "email", "profile"]
    )
    # Return in the format expected by the frontend
    # auth_url is a string, not a dict
    return {"authorization_url": auth_url}

# Custom callback that handles pending users properly
@app.get("/auth/google/callback", name="auth:google.callback")
async def google_callback_custom(
    request: Request,
    code: str,
    state: str = None,
    manager: CustomUserManager = Depends(get_user_manager),
    strategy: JWTStrategy = Depends(get_jwt_strategy),
):
    try:
        # Get OAuth token
        token = await google_oauth_client.get_access_token(code, request.url_for("auth:google.callback"))

        # Get user info
        user_info = await google_oauth_client.get_id_email(token["access_token"])
        account_id = user_info[0]
        account_email = user_info[1]

        # Call our oauth_callback to create/get user
        user = await manager.oauth_callback(
            oauth_name="google",
            access_token=token["access_token"],
            account_id=account_id,
            account_email=account_email,
            expires_at=token.get("expires_at"),
            refresh_token=token.get("refresh_token"),
            associate_by_email=True,
            is_verified_by_default=False,
        )

        print(f"OAuth callback returned user: {user.email}, is_active={user.is_active}, is_suspended={getattr(user, 'is_suspended', None)}")

        # Check if user is suspended
        is_suspended = getattr(user, 'is_suspended', None)
        if is_suspended is None or is_suspended is False or is_suspended == 0:
            is_suspended = False
        else:
            is_suspended = True

        if is_suspended:
            return templates.TemplateResponse("suspended.html", {"request": request})

        # Check if user is pending approval
        if not user.is_active:
            return templates.TemplateResponse("pending_approval.html", {"request": request})

        # User is active - log them in
        token_str = await strategy.write_token(user)

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Login Successful</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                .spinner {{ border: 4px solid #f3f3f3; border-top: 4px solid #3498db;
                           border-radius: 50%; width: 40px; height: 40px;
                           animation: spin 1s linear infinite; margin: 20px auto; }}
                @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
            </style>
        </head>
        <body>
            <h1>Login Successful!</h1>
            <div class="spinner"></div>
            <p>Redirecting...</p>
            <script>
                setTimeout(function() {{
                    window.location.href = '/dashboard';
                }}, 500);
            </script>
        </body>
        </html>
        """

        response = HTMLResponse(content=html_content, status_code=200)
        response.set_cookie(
            key="auth_cookie",
            value=token_str,
            httponly=True,
            max_age=3600,
            samesite="lax"
        )
        return response

    except Exception as e:
        print(f"ERROR in OAuth callback endpoint: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse("login.html", {"request": request, "error": "oauth_failed"})

# Note: OAuth middleware removed - custom callback handles everything

# Landing page - redirects based on authentication status and user type
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    # Try to get current user
    cookie = request.cookies.get("auth_cookie")
    
    if not cookie:
        # Not logged in, go to login page
        return RedirectResponse("/login")
    
    # Try to decode token and get user
    try:
        async with async_session_maker() as session:
            payload = jwt.decode(
                cookie, 
                SECRET, 
                algorithms=["HS256"],
                options={"verify_aud": False}
            )
            user_id = payload.get("sub")
            
            if user_id:
                user_id = int(user_id)
                result = await session.execute(select(User).where(User.id == user_id))
                user = result.scalars().first()

                if user:
                    # Check if user is suspended (handle None as False)
                    is_suspended = getattr(user, 'is_suspended', None)
                    is_active = user.is_active

                    print(f"Root route check for {user.email}: is_suspended={is_suspended}, is_active={is_active}")

                    # Normalize is_suspended to boolean (handle None, 0, 1, True, False)
                    if is_suspended is None or is_suspended is False or is_suspended == 0:
                        is_suspended = False
                    else:
                        is_suspended = True

                    if is_suspended:
                        print(f"Root route: {user.email} is SUSPENDED - showing suspended page")
                        response = templates.TemplateResponse("suspended.html", {"request": request}, status_code=403)
                        response.delete_cookie("auth_cookie")
                        return response

                    # Check if user is pending approval
                    if not is_active:
                        print(f"Root route: {user.email} is PENDING - showing pending approval page")
                        response = templates.TemplateResponse("pending_approval.html", {"request": request}, status_code=403)
                        response.delete_cookie("auth_cookie")
                        return response

                    # User is active and not suspended - redirect to dashboard
                    if user.is_superuser:
                        return RedirectResponse("/dashboard")
                    else:
                        return RedirectResponse("/dashboard")
    except:
        pass

    # If anything fails, go to login
    return RedirectResponse("/login")

# Login page
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

# Registration page
@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

# Registration form handler
@app.post("/auth/register")
async def register_user(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    manager: CustomUserManager = Depends(get_user_manager)
):
    try:
        user_create = UserCreate(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_active=False,  # Pending approval
            is_verified=False,
            is_suspended=False  # Explicitly set not suspended
        )
        await manager.create(user_create)
        return templates.TemplateResponse("registration_pending.html", {"request": request})
    except exceptions.UserAlreadyExists:
        return templates.TemplateResponse("register.html", {
            "request": request, 
            "error": "A user with this email already exists"
        })
    except Exception as e:
        return templates.TemplateResponse("register.html", {
            "request": request, 
            "error": "Registration failed. Please try again."
        })

# JWT login form handler (for admin password login)
@app.post("/auth/jwt/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    manager: CustomUserManager = Depends(get_user_manager),
    strategy: JWTStrategy = Depends(get_jwt_strategy)
):
    from fastapi.security import OAuth2PasswordRequestForm
    
    # Create credentials object
    credentials = OAuth2PasswordRequestForm(username=username, password=password, scope="")
    
    try:
        user = await manager.authenticate(credentials)
        
        if user is None:
            return RedirectResponse("/login?error=invalid_credentials", status_code=303)
        
        # Create token
        token = await strategy.write_token(user)
        
        # Redirect based on user type - admins go to users page, regular users go to dashboard
        redirect_url = "/dashboard"
        response = RedirectResponse(redirect_url, status_code=303)
        response.set_cookie(
            key="auth_cookie",
            value=token,
            httponly=True,
            max_age=3600,
            samesite="lax"
        )
        return response
        
    except HTTPException as e:
        if e.detail == "PENDING_APPROVAL":
            return templates.TemplateResponse("pending_approval.html", {"request": request})
        elif e.detail == "SUSPENDED":
            return templates.TemplateResponse("suspended.html", {"request": request})
        return RedirectResponse("/login?error=invalid_credentials", status_code=303)
    except Exception as e:
        print(f"Login error: {e}")
        return RedirectResponse("/login?error=server_error", status_code=303)

# Logout
@app.get("/auth/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("auth_cookie")
    return response

# Get current user info API
@app.get("/api/user/me")
async def get_current_user_info(user: User = Depends(current_user)):
    return {
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_superuser": user.is_superuser,
        "is_active": user.is_active
    }

# Get dashboard preferences
@app.get("/api/user/dashboard-preferences")
async def get_dashboard_preferences(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    # Refresh user from database to get latest preferences
    result = await session.execute(select(User).where(User.id == user.id))
    db_user = result.scalars().first()

    if db_user and db_user.dashboard_preferences:
        try:
            import json
            return json.loads(db_user.dashboard_preferences)
        except:
            return {}
    return {}

# Save dashboard preferences
@app.post("/api/user/dashboard-preferences")
async def save_dashboard_preferences(
    preferences: Dict[str, Any],
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    import json

    # Get user from database
    result = await session.execute(select(User).where(User.id == user.id))
    db_user = result.scalars().first()

    if not db_user:
        raise HTTPException(404, "User not found")

    # Save preferences as JSON string
    db_user.dashboard_preferences = json.dumps(preferences)
    await session.commit()

    return {"status": "success", "message": "Preferences saved"}

# Dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})

# Devices page
@app.get("/devices", response_class=HTMLResponse)
async def devices_page(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse("devices.html", {"request": request, "user": user})

# Plants page
@app.get("/plants", response_class=HTMLResponse)
async def plants_page(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse("plants.html", {"request": request, "user": user})

# Admin: Overview page
@app.get("/admin/overview", response_class=HTMLResponse)
async def admin_overview_page(request: Request, admin: User = Depends(current_admin)):
    return templates.TemplateResponse("admin_overview.html", {"request": request, "user": admin})

# Admin: Get all devices
@app.get("/admin/all-devices")
async def get_all_devices(admin: User = Depends(current_admin), session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(Device, User.email)
        .join(User, Device.user_id == User.id)
        .order_by(Device.id.desc())
    )

    devices_list = []
    for device, owner_email in result.all():
        # Check for active plant assignment
        assignment_result = await session.execute(
            select(DeviceAssignment, Plant)
            .join(Plant, DeviceAssignment.plant_id == Plant.id)
            .where(
                DeviceAssignment.device_id == device.id,
                DeviceAssignment.removed_at == None
            )
        )
        assignment_row = assignment_result.first()

        active_plant_name = None
        active_phase = None

        if assignment_row:
            assignment, plant = assignment_row
            active_plant_name = plant.name
            active_phase = assignment.phase

        devices_list.append({
            "device_id": device.device_id,
            "name": device.name,
            "owner_email": owner_email,
            "device_type": device.device_type,
            "is_online": device.is_online,
            "active_plant_name": active_plant_name,
            "active_phase": active_phase
        })

    return devices_list

# Admin: Get all plants
@app.get("/admin/all-plants")
async def get_all_plants(admin: User = Depends(current_admin), session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(Plant, User.email, Device.device_id)
        .join(User, Plant.user_id == User.id)
        .outerjoin(Device, Plant.device_id == Device.id)
        .order_by(Plant.id.desc())
    )

    plants_list = []
    for plant, owner_email, device_uuid in result.all():
        plants_list.append({
            "plant_id": plant.plant_id,
            "name": plant.name,
            "owner_email": owner_email,
            "device_id": device_uuid,
            "status": plant.status,
            "current_phase": plant.current_phase,
            "start_date": plant.start_date.isoformat() if plant.start_date else None,
            "end_date": plant.end_date.isoformat() if plant.end_date else None,
            "is_active": plant.end_date is None
        })

    return plants_list

# Admin: Get user count
@app.get("/admin/user-count")
async def get_user_count(admin: User = Depends(current_admin), session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(func.count(User.id)))
    count = result.scalar()
    return {"count": count}

# Admin: Users page
@app.get("/admin/users", response_class=HTMLResponse)
async def users_page(request: Request, admin: User = Depends(current_admin), session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(User).options(selectinload(User.oauth_accounts))
    )
    users = result.scalars().all()
    return templates.TemplateResponse("users.html", {"request": request, "user": admin, "users": users})

# Admin: Add user
@app.post("/admin/users")
async def add_user(
    user_data: UserCreate,
    admin: User = Depends(current_admin),
    manager: CustomUserManager = Depends(get_user_manager)
):
    try:
        user = await manager.create(user_data)
        return {"status": "success", "user_id": user.id}
    except exceptions.UserAlreadyExists:
        raise HTTPException(400, "User already exists")

# Admin: Update user
@app.patch("/admin/users/{user_id}")
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    admin: User = Depends(current_admin),
    manager: CustomUserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_db)
):
    user = await manager.user_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    update_dict = {}
    if user_data.email is not None:
        update_dict["email"] = user_data.email
    if user_data.first_name is not None:
        update_dict["first_name"] = user_data.first_name
    if user_data.last_name is not None:
        update_dict["last_name"] = user_data.last_name
    if user_data.is_active is not None:
        update_dict["is_active"] = user_data.is_active
    if user_data.is_superuser is not None:
        update_dict["is_superuser"] = user_data.is_superuser
    
    user = await manager.user_db.update(user, update_dict)
    return {"status": "success"}

# Admin: Reset password
@app.post("/admin/users/{user_id}/reset-password")
async def reset_password(user_id: int, password_reset: PasswordReset, admin: User = Depends(current_admin), manager: CustomUserManager = Depends(get_user_manager)):
    user = await manager.user_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    hashed_password = manager.password_helper.hash(password_reset.password)
    update_dict = {"hashed_password": hashed_password}
    user = await manager.user_db.update(user, update_dict)
    return {"status": "success"}

# Admin: Suspend user
@app.post("/admin/users/{user_id}/suspend")
async def suspend_user(user_id: int, admin: User = Depends(current_admin), manager: CustomUserManager = Depends(get_user_manager)):
    user = await manager.user_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    update_dict = {"is_suspended": True}
    user = await manager.user_db.update(user, update_dict)
    return {"status": "success"}

# Admin: Unsuspend user
@app.post("/admin/users/{user_id}/unsuspend")
async def unsuspend_user(user_id: int, admin: User = Depends(current_admin), manager: CustomUserManager = Depends(get_user_manager)):
    user = await manager.user_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    update_dict = {"is_suspended": False}
    user = await manager.user_db.update(user, update_dict)
    return {"status": "success"}

# Admin: Approve user (activate pending user)
@app.post("/admin/users/{user_id}/approve")
async def approve_user(user_id: int, admin: User = Depends(current_admin), manager: CustomUserManager = Depends(get_user_manager)):
    user = await manager.user_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    update_dict = {"is_active": True}
    user = await manager.user_db.update(user, update_dict)
    return {"status": "success"}

# Admin: Delete user
@app.delete("/admin/users/{user_id}")
async def delete_user_admin(user_id: int, session: AsyncSession = Depends(get_db), admin: User = Depends(current_admin)):
    user = await session.get(User, user_id)
    if user:
        await session.delete(user)
        await session.commit()
        return {"status": "success"}
    raise HTTPException(404, "User not found")

# Added: Device create/add
class DeviceCreate(BaseModel):
    device_id: str
    name: Optional[str] = None

class DeviceRead(BaseModel):
    device_id: str
    name: Optional[str]
    is_online: bool
    is_owner: Optional[bool] = True  # Whether current user owns the device
    permission_level: Optional[str] = None  # 'viewer', 'controller', or None if owner
    shared_by_email: Optional[str] = None  # Email of owner if shared device
    active_plant_name: Optional[str] = None  # Name of currently assigned plant
    active_plant_id: Optional[str] = None  # ID of currently assigned plant
    active_phase: Optional[str] = None  # Current phase (veg, flower, drying)

# Device Sharing Pydantic models
class ShareCreate(BaseModel):
    permission_level: str  # 'viewer' or 'controller'

class ShareAccept(BaseModel):
    share_code: str

class ShareUpdate(BaseModel):
    permission_level: str

class ShareRead(BaseModel):
    id: int
    device_id: int
    share_code: str
    permission_level: str
    created_at: datetime
    expires_at: datetime
    accepted_at: Optional[datetime]
    is_active: bool
    shared_with_email: Optional[str]

# Plant Pydantic models
class PlantCreate(BaseModel):
    name: str  # Strain name
    system_id: Optional[str] = None
    device_id: str  # Device UUID

class PlantCreateNew(BaseModel):
    """New plant creation without device assignment"""
    name: str  # Strain name
    start_date: Optional[str] = None  # ISO format, defaults to now

class DeviceAssignmentCreate(BaseModel):
    """Assign a device to a plant for a specific phase"""
    device_id: str  # Device UUID
    phase: str  # 'feeding', 'curing', etc.

class PlantFinish(BaseModel):
    end_date: Optional[str] = None  # ISO format date string, defaults to today

class PlantYieldUpdate(BaseModel):
    yield_grams: float

class PlantRead(BaseModel):
    plant_id: str
    name: str
    system_id: Optional[str]
    device_id: Optional[str]  # Device UUID for display (legacy, may be None for new plants)
    start_date: datetime
    end_date: Optional[datetime]
    yield_grams: Optional[float]
    is_active: bool  # Computed: True if end_date is None
    status: str  # 'created', 'feeding', 'harvested', 'curing', 'finished'
    current_phase: Optional[str]  # Current phase name
    harvest_date: Optional[datetime]
    cure_start_date: Optional[datetime]
    cure_end_date: Optional[datetime]

class DeviceAssignmentRead(BaseModel):
    id: int
    device_id: str  # Device UUID
    device_name: Optional[str]
    phase: str
    assigned_at: datetime
    removed_at: Optional[datetime]

class LogEntryCreate(BaseModel):
    event_type: str  # 'sensor' or 'dosing'
    sensor_name: Optional[str] = None
    value: Optional[float] = None
    dose_type: Optional[str] = None
    dose_amount_ml: Optional[float] = None
    timestamp: str  # ISO format datetime string

class LogEntryRead(BaseModel):
    id: int
    event_type: str
    sensor_name: Optional[str]
    value: Optional[float]
    dose_type: Optional[str]
    dose_amount_ml: Optional[float]
    timestamp: datetime

@app.post("/user/devices", response_model=Dict[str, str])
async def add_device(device: DeviceCreate, user: User = Depends(current_user), session: AsyncSession = Depends(get_db)):
    existing = await session.execute(select(Device).where(Device.device_id == device.device_id))
    if existing.scalars().first():
        raise HTTPException(400, "Device ID already linked")
    
    api_key = secrets.token_hex(32)
    
    new_device = Device(
        device_id=device.device_id,
        api_key=api_key,
        name=device.name,
        user_id=user.id
    )
    session.add(new_device)
    await session.commit()
    await session.refresh(new_device)
    
    return {"api_key": api_key, "message": "Device added. Copy API key to Pi settings."}

# Added: List user devices (owned and shared)
@app.get("/user/devices", response_model=List[DeviceRead])
async def list_devices(user: User = Depends(current_user), session: AsyncSession = Depends(get_db)):
    devices_list = []

    # Get owned devices
    owned_result = await session.execute(select(Device).where(Device.user_id == user.id))
    for device in owned_result.scalars().all():
        # Check for active plant assignment
        assignment_result = await session.execute(
            select(DeviceAssignment, Plant)
            .join(Plant, DeviceAssignment.plant_id == Plant.id)
            .where(
                DeviceAssignment.device_id == device.id,
                DeviceAssignment.removed_at == None
            )
        )
        assignment_row = assignment_result.first()

        active_plant_name = None
        active_plant_id = None
        active_phase = None

        if assignment_row:
            assignment, plant = assignment_row
            active_plant_name = plant.name
            active_plant_id = plant.plant_id
            active_phase = assignment.phase

        devices_list.append(DeviceRead(
            device_id=device.device_id,
            name=device.name,
            is_online=device.is_online,
            is_owner=True,
            permission_level=None,
            shared_by_email=None,
            active_plant_name=active_plant_name,
            active_plant_id=active_plant_id,
            active_phase=active_phase
        ))

    # Get shared devices
    shared_result = await session.execute(
        select(Device, DeviceShare, User.email)
        .join(DeviceShare, DeviceShare.device_id == Device.id)
        .join(User, DeviceShare.owner_user_id == User.id)
        .where(
            DeviceShare.shared_with_user_id == user.id,
            DeviceShare.is_active == True,
            DeviceShare.revoked_at == None,
            DeviceShare.accepted_at != None
        )
    )

    for device, share, owner_email in shared_result.all():
        # Check for active plant assignment
        assignment_result = await session.execute(
            select(DeviceAssignment, Plant)
            .join(Plant, DeviceAssignment.plant_id == Plant.id)
            .where(
                DeviceAssignment.device_id == device.id,
                DeviceAssignment.removed_at == None
            )
        )
        assignment_row = assignment_result.first()

        active_plant_name = None
        active_plant_id = None
        active_phase = None

        if assignment_row:
            assignment, plant = assignment_row
            active_plant_name = plant.name
            active_plant_id = plant.plant_id
            active_phase = assignment.phase

        devices_list.append(DeviceRead(
            device_id=device.device_id,
            name=device.name,
            is_online=device.is_online,
            is_owner=False,
            permission_level=share.permission_level,
            shared_by_email=owner_email,
            active_plant_name=active_plant_name,
            active_plant_id=active_plant_id,
            active_phase=active_phase
        ))

    return devices_list

# Added: Delete device
@app.delete("/user/devices/{device_id}")
async def delete_device(device_id: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_db)):
    # Load device with its related plants to allow proper cascade deletion
    result = await session.execute(
        select(Device)
        .options(selectinload(Device.plants))
        .where(Device.device_id == device_id, Device.user_id == user.id)
    )
    device = result.scalars().first()
    if not device:
        raise HTTPException(404, "Device not found")

    # Delete all associated plants first (which will cascade delete logs)
    if device.plants:
        for plant in device.plants:
            await session.delete(plant)

    # Now delete the device
    await session.delete(device)
    await session.commit()
    return {"status": "success"}

# Helper function to generate unique share code
async def generate_share_code(session: AsyncSession) -> str:
    """Generate a unique 10-character alphanumeric share code."""
    import string
    import random

    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.ascii_lowercase + string.digits, k=10))
        # Check if code already exists
        result = await session.execute(select(DeviceShare).where(DeviceShare.share_code == code))
        if not result.scalars().first():
            return code

# Create a share link for a device
@app.post("/user/devices/{device_id}/share", response_model=Dict[str, str])
async def create_share(
    device_id: str,
    share_data: ShareCreate,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    # Verify user owns the device
    result = await session.execute(select(Device).where(Device.device_id == device_id, Device.user_id == user.id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(404, "Device not found or not owned by you")

    # Validate permission level
    if share_data.permission_level not in ['viewer', 'controller']:
        raise HTTPException(400, "Invalid permission level. Must be 'viewer' or 'controller'")

    # Generate unique share code
    share_code = await generate_share_code(session)

    # Create share
    share = DeviceShare(
        device_id=device.id,
        owner_user_id=user.id,
        share_code=share_code,
        permission_level=share_data.permission_level,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        is_active=True
    )

    session.add(share)
    await session.commit()
    await session.refresh(share)

    return {"share_code": share_code, "expires_at": share.expires_at.isoformat()}

# Accept a share with a code
@app.post("/user/devices/accept-share", response_model=Dict[str, str])
async def accept_share(
    share_data: ShareAccept,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    # Find the share by code
    result = await session.execute(
        select(DeviceShare).where(
            DeviceShare.share_code == share_data.share_code,
            DeviceShare.is_active == True,
            DeviceShare.accepted_at == None
        )
    )
    share = result.scalars().first()

    if not share:
        raise HTTPException(404, "Invalid or already accepted share code")

    # Check if expired
    if datetime.utcnow() > share.expires_at:
        share.is_active = False
        await session.commit()
        raise HTTPException(400, "Share code has expired")

    # Check if user is trying to share with themselves
    if share.owner_user_id == user.id:
        raise HTTPException(400, "You cannot accept your own share")

    # Accept the share
    share.shared_with_user_id = user.id
    share.accepted_at = datetime.utcnow()

    await session.commit()
    await session.refresh(share)

    # Get device info
    device_result = await session.execute(select(Device).where(Device.id == share.device_id))
    device = device_result.scalars().first()

    return {"status": "success", "device_id": device.device_id if device else "unknown"}

# List all shares for a device (for owner only)
@app.get("/user/devices/{device_id}/shares", response_model=List[ShareRead])
async def list_shares(
    device_id: str,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    # Verify user owns the device
    result = await session.execute(select(Device).where(Device.device_id == device_id, Device.user_id == user.id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(404, "Device not found or not owned by you")

    # Get all active shares for this device
    result = await session.execute(
        select(DeviceShare, User.email)
        .outerjoin(User, DeviceShare.shared_with_user_id == User.id)
        .where(
            DeviceShare.device_id == device.id,
            DeviceShare.is_active == True,
            DeviceShare.revoked_at == None
        )
    )

    shares_data = []
    for share, email in result.all():
        shares_data.append(ShareRead(
            id=share.id,
            device_id=share.device_id,
            share_code=share.share_code,
            permission_level=share.permission_level,
            created_at=share.created_at,
            expires_at=share.expires_at,
            accepted_at=share.accepted_at,
            is_active=share.is_active,
            shared_with_email=email
        ))

    return shares_data

# Revoke a share
@app.delete("/user/devices/shares/{share_id}")
async def revoke_share(
    share_id: int,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    # Find the share and verify ownership
    result = await session.execute(
        select(DeviceShare).where(
            DeviceShare.id == share_id,
            DeviceShare.owner_user_id == user.id
        )
    )
    share = result.scalars().first()

    if not share:
        raise HTTPException(404, "Share not found or not owned by you")

    # Revoke the share
    share.is_active = False
    share.revoked_at = datetime.utcnow()

    await session.commit()

    return {"status": "success"}

# Update share permission
@app.put("/user/devices/shares/{share_id}/permission")
async def update_share_permission(
    share_id: int,
    share_data: ShareUpdate,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    # Validate permission level
    if share_data.permission_level not in ['viewer', 'controller']:
        raise HTTPException(400, "Invalid permission level. Must be 'viewer' or 'controller'")

    # Find the share and verify ownership
    result = await session.execute(
        select(DeviceShare).where(
            DeviceShare.id == share_id,
            DeviceShare.owner_user_id == user.id
        )
    )
    share = result.scalars().first()

    if not share:
        raise HTTPException(404, "Share not found or not owned by you")

    # Update permission
    share.permission_level = share_data.permission_level

    await session.commit()

    return {"status": "success", "permission_level": share.permission_level}

# Plant Management API Endpoints

# Create a new plant (start plant) - for devices using API key
@app.post("/api/devices/{device_id}/plants", response_model=Dict[str, str])
async def create_plant_device(
    device_id: str,
    plant_data: PlantCreate,
    api_key: str = Query(...),
    session: AsyncSession = Depends(get_db)
):
    # Verify device and API key
    result = await session.execute(select(Device).where(Device.device_id == device_id, Device.api_key == api_key))
    device = result.scalars().first()

    if not device:
        raise HTTPException(401, "Invalid device or API key")

    # Generate unique plant_id using timestamp
    from datetime import datetime
    plant_id = str(int(datetime.utcnow().timestamp() * 1000000))  # Microsecond precision

    # Create plant
    new_plant = Plant(
        plant_id=plant_id,
        name=plant_data.name,
        system_id=plant_data.system_id,
        device_id=device.id,
        user_id=device.user_id,  # Plant belongs to device owner
        start_date=datetime.utcnow()
    )

    session.add(new_plant)
    await session.commit()
    await session.refresh(new_plant)

    return {"plant_id": plant_id, "message": "Plant started successfully"}

# Create a new plant (start plant) - for logged-in users
@app.post("/user/plants", response_model=Dict[str, str])
async def create_plant(
    plant_data: PlantCreate,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    # Verify device exists and user has access (owns or has controller permission)
    result = await session.execute(select(Device).where(Device.device_id == plant_data.device_id))
    device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    # Check if user owns device
    is_owner = device.user_id == user.id

    # If not owner, check if user has controller permission
    if not is_owner:
        result = await session.execute(
            select(DeviceShare).where(
                DeviceShare.device_id == device.id,
                DeviceShare.shared_with_user_id == user.id,
                DeviceShare.is_active == True,
                DeviceShare.revoked_at == None,
                DeviceShare.accepted_at != None,
                DeviceShare.permission_level == 'controller'
            )
        )
        share = result.scalars().first()

        if not share:
            raise HTTPException(403, "You don't have permission to create plants on this device")

    # Generate unique plant_id using timestamp
    from datetime import datetime
    plant_id = str(int(datetime.utcnow().timestamp() * 1000000))  # Microsecond precision

    # Create plant
    new_plant = Plant(
        plant_id=plant_id,
        name=plant_data.name,
        system_id=plant_data.system_id,
        device_id=device.id,
        user_id=device.user_id,  # Plant belongs to device owner
        start_date=datetime.utcnow()
    )

    session.add(new_plant)
    await session.commit()
    await session.refresh(new_plant)

    return {"plant_id": plant_id, "message": "Plant started successfully"}

# NEW: Create a plant without device assignment - server-side creation
@app.post("/user/plants/new", response_model=Dict[str, str])
async def create_plant_new(
    plant_data: PlantCreateNew,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    """Create a new plant on the server without assigning it to a device yet"""
    from datetime import datetime

    # Generate unique plant_id using timestamp
    plant_id = str(int(datetime.utcnow().timestamp() * 1000000))  # Microsecond precision

    # Parse start_date if provided, otherwise use current time
    if plant_data.start_date:
        try:
            start_date = date_parser.parse(plant_data.start_date)
        except:
            raise HTTPException(400, "Invalid start_date format. Use ISO format.")
    else:
        start_date = datetime.utcnow()

    # Create plant with status='created', no device assignment yet
    new_plant = Plant(
        plant_id=plant_id,
        name=plant_data.name,
        user_id=user.id,
        start_date=start_date,
        status='created',  # Not assigned to any device yet
        device_id=None,  # No device initially
        system_id=None
    )

    session.add(new_plant)
    await session.commit()
    await session.refresh(new_plant)

    return {"plant_id": plant_id, "message": "Plant created successfully. Assign it to a device to start monitoring."}

# Get assignments for a plant
@app.get("/user/plants/{plant_id}/assignments")
async def get_plant_assignments(
    plant_id: str,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    """Get all device assignments for a plant"""
    # Get the plant
    result = await session.execute(select(Plant).where(Plant.plant_id == plant_id))
    plant = result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found")

    # Verify user owns the plant
    if plant.user_id != user.id:
        raise HTTPException(403, "You don't have permission to view this plant")

    # Get active assignments
    result = await session.execute(
        select(DeviceAssignment, Device)
        .join(Device, DeviceAssignment.device_id == Device.id)
        .where(
            DeviceAssignment.plant_id == plant.id,
            DeviceAssignment.removed_at == None
        )
        .order_by(DeviceAssignment.assigned_at.desc())
    )

    assignments_list = []
    for assignment, device in result.all():
        assignments_list.append({
            "device_id": device.device_id,
            "device_name": device.name,
            "phase": assignment.phase,
            "assigned_at": assignment.assigned_at.isoformat()
        })

    return assignments_list

# NEW: Assign a device to a plant for a specific phase
@app.post("/user/plants/{plant_id}/assign", response_model=Dict[str, str])
async def assign_device_to_plant(
    plant_id: str,
    assignment_data: DeviceAssignmentCreate,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    """Assign a device to monitor a plant during a specific phase"""
    from datetime import datetime

    # Get the plant
    result = await session.execute(select(Plant).where(Plant.plant_id == plant_id))
    plant = result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found")

    # Verify user owns the plant
    if plant.user_id != user.id:
        raise HTTPException(403, "You don't have permission to modify this plant")

    # Get the device
    result = await session.execute(select(Device).where(Device.device_id == assignment_data.device_id))
    device = result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    # Verify user owns or has controller access to the device
    is_owner = device.user_id == user.id

    if not is_owner:
        result = await session.execute(
            select(DeviceShare).where(
                DeviceShare.device_id == device.id,
                DeviceShare.shared_with_user_id == user.id,
                DeviceShare.is_active == True,
                DeviceShare.revoked_at == None,
                DeviceShare.accepted_at != None,
                DeviceShare.permission_level == 'controller'
            )
        )
        share = result.scalars().first()

        if not share:
            raise HTTPException(403, "You don't have permission to use this device")

    # Check if there's already an active assignment for this plant and phase
    result = await session.execute(
        select(DeviceAssignment).where(
            DeviceAssignment.plant_id == plant.id,
            DeviceAssignment.phase == assignment_data.phase,
            DeviceAssignment.removed_at == None
        )
    )
    existing_assignment = result.scalars().first()

    if existing_assignment:
        raise HTTPException(400, f"Plant already has an active assignment for phase '{assignment_data.phase}'")

    # Create the assignment
    new_assignment = DeviceAssignment(
        plant_id=plant.id,
        device_id=device.id,
        phase=assignment_data.phase,
        assigned_at=datetime.utcnow()
    )

    session.add(new_assignment)

    # Update plant status and phase
    plant.current_phase = assignment_data.phase

    # Update status based on phase
    if assignment_data.phase == 'veg':
        plant.status = 'veg'
    elif assignment_data.phase == 'flower':
        plant.status = 'flower'
    elif assignment_data.phase == 'drying':
        plant.status = 'drying'
        if not plant.cure_start_date:
            plant.cure_start_date = datetime.utcnow()

    await session.commit()

    # Send websocket notification to device
    if assignment_data.device_id in device_connections:
        try:
            await device_connections[assignment_data.device_id].send_json({
                "command": "assign_plant",
                "plant_id": plant.plant_id,
                "plant_name": plant.name,
                "phase": assignment_data.phase,
                "system_id": plant.system_id or f"Zone{plant.plant_id[-1]}"  # Fallback system_id
            })
            print(f"[WS] Sent assign_plant to device {assignment_data.device_id}")
        except Exception as e:
            print(f"[WS] Failed to send assign_plant to device: {e}")

    return {"message": f"Device assigned to plant for {assignment_data.phase} phase"}

# NEW: Unassign a device from a plant (end a phase)
@app.post("/user/plants/{plant_id}/unassign", response_model=Dict[str, str])
async def unassign_device_from_plant(
    plant_id: str,
    phase: str = Body(..., embed=True),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    """Remove a device assignment from a plant (end a monitoring phase)"""
    from datetime import datetime

    # Get the plant
    result = await session.execute(select(Plant).where(Plant.plant_id == plant_id))
    plant = result.scalars().first()

    if not plant:
        raise HTTPException(404, "Plant not found")

    # Verify user owns the plant
    if plant.user_id != user.id:
        raise HTTPException(403, "You don't have permission to modify this plant")

    # Find the active assignment for this phase
    result = await session.execute(
        select(DeviceAssignment).where(
            DeviceAssignment.plant_id == plant.id,
            DeviceAssignment.phase == phase,
            DeviceAssignment.removed_at == None
        )
    )
    assignment = result.scalars().first()

    if not assignment:
        raise HTTPException(404, f"No active assignment found for phase '{phase}'")

    # Get device info before marking removed
    result = await session.execute(select(Device).where(Device.id == assignment.device_id))
    device = result.scalars().first()

    # Mark the assignment as removed
    assignment.removed_at = datetime.utcnow()

    # Update plant status based on what phase ended
    if phase in ['veg', 'flower']:
        plant.status = 'harvested'
        plant.harvest_date = datetime.utcnow()
        plant.current_phase = None
    elif phase == 'drying':
        plant.status = 'finished'
        plant.cure_end_date = datetime.utcnow()
        plant.current_phase = None
        plant.end_date = datetime.utcnow()  # Final completion

    await session.commit()

    # Send websocket notification to device
    if device and device.device_id in device_connections:
        try:
            await device_connections[device.device_id].send_json({
                "command": "unassign_plant",
                "plant_id": plant.plant_id
            })
            print(f"[WS] Sent unassign_plant to device {device.device_id}")
        except Exception as e:
            print(f"[WS] Failed to send unassign_plant to device: {e}")

    return {"message": f"Device unassigned from plant, {phase} phase ended"}

# List all plants for user (owned or device-assigned)
@app.get("/user/plants", response_model=List[PlantRead])
async def list_plants(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    active_only: bool = False
):
    # Get all plants owned by user (both legacy device-owned and new server-created plants)
    # Use outer join since device_id can be None for new plants
    query = select(Plant, Device.device_id).outerjoin(Device, Plant.device_id == Device.id).where(Plant.user_id == user.id).order_by(Plant.display_order, Plant.id)

    if active_only:
        query = query.where(Plant.status.in_(['created', 'veg', 'flower', 'drying', 'harvested', 'feeding', 'curing']))  # Not finished

    result = await session.execute(query)

    plants_list = []
    for plant, device_uuid in result.all():
        plants_list.append(PlantRead(
            plant_id=plant.plant_id,
            name=plant.name,
            system_id=plant.system_id,
            device_id=device_uuid,  # May be None for new plants
            start_date=plant.start_date,
            end_date=plant.end_date,
            yield_grams=plant.yield_grams,
            is_active=(plant.end_date is None),
            status=plant.status,
            current_phase=plant.current_phase,
            harvest_date=plant.harvest_date,
            cure_start_date=plant.cure_start_date,
            cure_end_date=plant.cure_end_date
        ))

    return plants_list

# Get a specific plant
@app.get("/user/plants/{plant_id}", response_model=PlantRead)
async def get_plant(
    plant_id: str,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    # Get plant with device info (use outer join since device_id can be None)
    result = await session.execute(
        select(Plant, Device.device_id)
        .outerjoin(Device, Plant.device_id == Device.id)
        .where(Plant.plant_id == plant_id, Plant.user_id == user.id)
    )

    row = result.first()
    if not row:
        raise HTTPException(404, "Plant not found")

    plant, device_uuid = row

    return PlantRead(
        plant_id=plant.plant_id,
        name=plant.name,
        system_id=plant.system_id,
        device_id=device_uuid,
        start_date=plant.start_date,
        end_date=plant.end_date,
        yield_grams=plant.yield_grams,
        is_active=(plant.end_date is None),
        status=plant.status,
        current_phase=plant.current_phase,
        harvest_date=plant.harvest_date,
        cure_start_date=plant.cure_start_date,
        cure_end_date=plant.cure_end_date
    )

# Finish a plant - for devices using API key
@app.post("/api/devices/{device_id}/plants/{plant_id}/finish", response_model=Dict[str, str])
async def finish_plant_device(
    device_id: str,
    plant_id: str,
    finish_data: PlantFinish,
    api_key: str = Query(...),
    session: AsyncSession = Depends(get_db)
):
    # Verify device and API key
    result = await session.execute(select(Device).where(Device.device_id == device_id, Device.api_key == api_key))
    device = result.scalars().first()

    if not device:
        raise HTTPException(401, "Invalid device or API key")

    # Get plant and verify it belongs to this device
    result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id, Plant.device_id == device.id)
    )

    plant = result.scalars().first()
    if not plant:
        raise HTTPException(404, "Plant not found for this device")

    # Check if plant is already finished
    if plant.end_date is not None:
        raise HTTPException(400, "Plant is already finished")

    # Parse end_date or use current datetime
    if finish_data.end_date:
        try:
            end_date = date_parser.isoparse(finish_data.end_date)
        except Exception as e:
            raise HTTPException(400, f"Invalid date format. Use ISO 8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS). Error: {str(e)}")
    else:
        end_date = datetime.utcnow()

    # Update plant
    plant.end_date = end_date
    await session.commit()

    return {"status": "success", "message": "Plant finished successfully"}

# Finish a plant - for logged-in users
@app.post("/user/plants/{plant_id}/finish", response_model=Dict[str, str])
async def finish_plant(
    plant_id: str,
    finish_data: PlantFinish,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    # Get plant and verify ownership
    result = await session.execute(
        select(Plant, Device)
        .join(Device, Plant.device_id == Device.id)
        .where(Plant.plant_id == plant_id, Device.user_id == user.id)
    )

    row = result.first()
    if not row:
        raise HTTPException(404, "Plant not found")

    plant, device = row

    # Check if plant is already finished
    if plant.end_date is not None:
        raise HTTPException(400, "Plant is already finished")

    # Parse end_date or use current datetime
    if finish_data.end_date:
        try:
            end_date = date_parser.isoparse(finish_data.end_date)
        except Exception as e:
            raise HTTPException(400, f"Invalid date format. Use ISO 8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS). Error: {str(e)}")
    else:
        end_date = datetime.utcnow()

    # Update plant
    plant.end_date = end_date
    await session.commit()

    return {"status": "success", "message": "Plant finished successfully"}

# Update yield for finished plant
@app.patch("/user/plants/{plant_id}/yield", response_model=Dict[str, str])
async def update_plant_yield(
    plant_id: str,
    yield_data: PlantYieldUpdate,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    # Get plant and verify ownership
    result = await session.execute(
        select(Plant, Device)
        .join(Device, Plant.device_id == Device.id)
        .where(Plant.plant_id == plant_id, Device.user_id == user.id)
    )

    row = result.first()
    if not row:
        raise HTTPException(404, "Plant not found")

    plant, device = row

    # Update yield
    plant.yield_grams = yield_data.yield_grams
    await session.commit()

    return {"status": "success", "message": "Yield updated successfully"}

# Delete a plant (admin only)
@app.delete("/user/plants/{plant_id}", response_model=Dict[str, str])
async def delete_plant_user(
    plant_id: str,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    # Get plant
    result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id)
    )

    plant = result.scalars().first()
    if not plant:
        raise HTTPException(404, "Plant not found")

    # Check if user owns this plant
    if plant.user_id != user.id:
        raise HTTPException(403, "You don't have permission to delete this plant")

    # Delete plant (logs will be cascade deleted)
    await session.delete(plant)
    await session.commit()

    return {"status": "success", "message": f"Plant '{plant.name}' and all associated logs deleted successfully"}

# Reorder plants
@app.put("/user/plants/reorder")
async def reorder_plants(
    plant_order: List[str] = Body(...),  # List of plant_ids in desired order
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db)
):
    """Update the display order of plants for the current user"""
    # Verify all plants belong to user's devices
    result = await session.execute(
        select(Plant).join(Device, Plant.device_id == Device.id).where(
            Device.user_id == user.id,
            Plant.plant_id.in_(plant_order)
        )
    )
    plants = {plant.plant_id: plant for plant in result.scalars().all()}

    if len(plants) != len(plant_order):
        raise HTTPException(400, "Some plant IDs not found or not owned by user")

    # Update display_order for each plant
    for index, plant_id in enumerate(plant_order):
        plants[plant_id].display_order = index

    await session.commit()

    return {"status": "success", "message": f"Reordered {len(plant_order)} plants"}

@app.delete("/admin/plants/{plant_id}", response_model=Dict[str, str])
async def delete_plant_admin(
    plant_id: str,
    user: User = Depends(current_admin),
    session: AsyncSession = Depends(get_db)
):
    # Get plant
    result = await session.execute(
        select(Plant).where(Plant.plant_id == plant_id)
    )

    plant = result.scalars().first()
    if not plant:
        raise HTTPException(404, "Plant not found")

    # Delete plant (logs will be cascade deleted)
    await session.delete(plant)
    await session.commit()

    return {"status": "success", "message": f"Plant '{plant.name}' and all associated logs deleted successfully"}

# Log Management API Endpoints

# Upload logs (from pH dosing system using API key)
@app.post("/api/devices/{device_id}/logs", response_model=Dict[str, str])
async def upload_logs(
    device_id: str,
    logs: List[LogEntryCreate],
    api_key: str = Query(...),
    plant_id: str = Query(...),
    session: AsyncSession = Depends(get_db)
):
    # Verify device and API key
    result = await session.execute(select(Device).where(Device.device_id == device_id, Device.api_key == api_key))
    device = result.scalars().first()

    if not device:
        raise HTTPException(401, "Invalid device or API key")

    # Verify plant exists and belongs to this device
    result = await session.execute(select(Plant).where(Plant.plant_id == plant_id, Plant.device_id == device.id))
    plant = result.scalars().first()

    if not plant:
        print(f"[LOG UPLOAD ERROR] Plant not found: plant_id={plant_id}, device.id={device.id}, device.device_id={device_id}")
        # Check if plant exists at all
        check_result = await session.execute(select(Plant).where(Plant.plant_id == plant_id))
        check_plant = check_result.scalars().first()
        if check_plant:
            print(f"[LOG UPLOAD ERROR] Plant {plant_id} exists but belongs to device.id={check_plant.device_id}, not {device.id}")
        else:
            print(f"[LOG UPLOAD ERROR] Plant {plant_id} does not exist in database at all")
        raise HTTPException(404, f"Plant {plant_id} not found for device {device_id}")

    # Insert log entries (skip duplicates)
    log_count = 0
    skipped_count = 0
    for log_data in logs:
        try:
            # Parse timestamp
            timestamp = date_parser.isoparse(log_data.timestamp)

            # Check if this log entry already exists (duplicate detection)
            duplicate_check = await session.execute(
                select(LogEntry).where(
                    LogEntry.plant_id == plant.id,
                    LogEntry.timestamp == timestamp,
                    LogEntry.event_type == log_data.event_type
                )
            )
            existing_entry = duplicate_check.scalars().first()

            if existing_entry:
                skipped_count += 1
                continue  # Skip this duplicate entry

            # Create log entry
            log_entry = LogEntry(
                plant_id=plant.id,
                event_type=log_data.event_type,
                sensor_name=log_data.sensor_name,
                value=log_data.value,
                dose_type=log_data.dose_type,
                dose_amount_ml=log_data.dose_amount_ml,
                timestamp=timestamp
            )

            session.add(log_entry)
            log_count += 1
        except Exception as e:
            print(f"Error inserting log entry: {e}")
            # Continue with other log entries

    await session.commit()

    message = f"Uploaded {log_count} log entries"
    if skipped_count > 0:
        message += f", skipped {skipped_count} duplicates"
    return {"status": "success", "message": message}

# Get logs for a plant
@app.get("/user/plants/{plant_id}/logs", response_model=List[LogEntryRead])
async def get_plant_logs(
    plant_id: str,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 1000
):
    # Verify plant exists and user has access
    result = await session.execute(
        select(Plant, Device)
        .join(Device, Plant.device_id == Device.id)
        .where(Plant.plant_id == plant_id, Device.user_id == user.id)
    )

    row = result.first()
    if not row:
        raise HTTPException(404, "Plant not found")

    plant, device = row

    # Build query
    query = select(LogEntry).where(LogEntry.plant_id == plant.id)

    # Apply filters
    if start_date:
        try:
            start_dt = date_parser.isoparse(start_date)
            query = query.where(LogEntry.timestamp >= start_dt)
        except Exception as e:
            print(f"Error parsing start_date: {e}")
            raise HTTPException(400, f"Invalid start_date format: {str(e)}")

    if end_date:
        try:
            end_dt = date_parser.isoparse(end_date)
            query = query.where(LogEntry.timestamp <= end_dt)
        except Exception as e:
            print(f"Error parsing end_date: {e}")
            raise HTTPException(400, f"Invalid end_date format: {str(e)}")

    if event_type:
        query = query.where(LogEntry.event_type == event_type)

    # Order by timestamp and limit
    query = query.order_by(LogEntry.timestamp.desc()).limit(limit)

    try:
        result = await session.execute(query)
        logs = result.scalars().all()
    except Exception as e:
        print(f"Error executing logs query: {e}")
        raise HTTPException(500, f"Database error: {str(e)}")

    # Convert to response model
    logs_list = []
    for log in logs:
        try:
            logs_list.append(LogEntryRead(
                id=log.id,
                event_type=log.event_type,
                sensor_name=log.sensor_name,
                value=log.value,
                dose_type=log.dose_type,
                dose_amount_ml=log.dose_amount_ml,
                timestamp=log.timestamp
            ))
        except Exception as e:
            print(f"Error converting log entry {log.id}: {e}")
            continue

    return logs_list

# Added: Global connections for WS relay
device_connections: Dict[str, WebSocket] = {}
user_connections: Dict[str, List[WebSocket]] = defaultdict(list)

# Added: Device WS endpoint (for Pi)
@app.websocket("/ws/devices/{device_id}")
async def device_websocket(websocket: WebSocket, device_id: str, api_key: str = Query(...), session: AsyncSession = Depends(get_db)):
    await websocket.accept()
    print(f"Device connected: {device_id} with api_key {api_key}")  # Log connection accept

    # Get device and verify auth
    result = await session.execute(
        select(Device, User)
        .join(User, Device.user_id == User.id)
        .where(Device.device_id == device_id, Device.api_key == api_key)
    )
    row = result.first()
    if not row:
        print(f"Invalid device/auth for {device_id}")  # Log invalid auth
        await websocket.close()
        return

    device, user = row

    await session.execute(update(Device).where(Device.device_id == device_id).values(is_online=True))
    await session.commit()
    print(f"Set {device_id} online in DB")  # Log DB update
    device_connections[device_id] = websocket

    # Send owner info to device
    try:
        await websocket.send_json({
            "command": "server_info",
            "owner_email": user.email,
            "owner_name": user.email.split('@')[0]  # Use email prefix as name
        })
        print(f"Sent owner info to device {device_id}: {user.email}")
    except Exception as e:
        print(f"Failed to send owner info to device {device_id}: {e}")

    # Notify all connected users that the device is online
    for user_ws in user_connections[device_id]:
        try:
            await user_ws.send_json({"type": "device_status", "online": True})
        except:
            pass  # User might have disconnected

    try:
        while True:
            data = await websocket.receive_json()
            print(f"Received from device {device_id}: {json.dumps(data)}")  # Log incoming data
            # Relay to connected users
            for user_ws in user_connections[device_id]:
                await user_ws.send_json(data)
                print(f"Relayed to user for {device_id}: {json.dumps(data)}")  # Log relay
    except WebSocketDisconnect:
        print(f"Device disconnected: {device_id}")  # Log disconnect
        if device_id in device_connections:
            del device_connections[device_id]
        await session.execute(update(Device).where(Device.device_id == device_id).values(is_online=False))
        await session.commit()
        print(f"Set {device_id} offline in DB")  # Log DB update
        
        # Notify all connected users that the device went offline
        for user_ws in user_connections[device_id]:
            try:
                await user_ws.send_json({"error": "Device offline"})
            except:
                pass  # User might have already disconnected

@app.websocket("/ws/user/devices/{device_id}")
async def user_websocket(websocket: WebSocket, device_id: str):
    # Manual authentication for WebSocket
    cookie = websocket.cookies.get("auth_cookie")
    
    if not cookie:
        print(f"WebSocket auth failed: No cookie for device {device_id}")
        await websocket.close(code=1008, reason="No authentication cookie")
        return
    
    # Get user from cookie
    try:
        async with async_session_maker() as session:
            # Decode the JWT token directly - ignore audience claim
            try:
                # Don't verify audience for WebSocket connections
                payload = jwt.decode(
                    cookie, 
                    SECRET, 
                    algorithms=["HS256"],
                    options={"verify_aud": False}  # Disable audience verification
                )
                user_id = payload.get("sub")
                
                if not user_id:
                    print(f"WebSocket auth failed: No user_id in token for device {device_id}")
                    await websocket.close(code=1008, reason="Invalid token")
                    return
                
                # Parse user_id to int
                try:
                    user_id = int(user_id)
                except (ValueError, TypeError):
                    print(f"WebSocket auth failed: Invalid user_id format for device {device_id}")
                    await websocket.close(code=1008, reason="Invalid user ID")
                    return
                
            except jwt.ExpiredSignatureError:
                print(f"WebSocket auth failed: Expired token for device {device_id}")
                await websocket.close(code=1008, reason="Token expired")
                return
            except jwt.InvalidTokenError as e:
                print(f"WebSocket auth failed: Invalid token for device {device_id}: {e}")
                await websocket.close(code=1008, reason="Invalid token")
                return
            
            # Get user from database
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalars().first()
            
            if not user or not user.is_active:
                print(f"WebSocket auth failed: User not found or inactive for device {device_id}")
                await websocket.close(code=1008, reason="User not active")
                return
            
            # Check if user owns this device OR has it shared with them
            result = await session.execute(select(Device).where(Device.device_id == device_id, Device.user_id == user.id))
            device = result.scalars().first()

            # If not owner, check if device is shared with user
            if not device:
                # Get device first
                result = await session.execute(select(Device).where(Device.device_id == device_id))
                device = result.scalars().first()

                if not device:
                    print(f"WebSocket auth failed: Device {device_id} not found")
                    await websocket.close(code=1008, reason="Device not found")
                    return

                # Check if device is shared with this user
                result = await session.execute(
                    select(DeviceShare).where(
                        DeviceShare.device_id == device.id,
                        DeviceShare.shared_with_user_id == user.id,
                        DeviceShare.is_active == True,
                        DeviceShare.revoked_at == None,
                        DeviceShare.accepted_at != None
                    )
                )
                share = result.scalars().first()

                if not share:
                    print(f"WebSocket auth failed: Device {device_id} not owned or shared with user {user_id}")
                    await websocket.close(code=1008, reason="Access denied")
                    return

            print(f"WebSocket authenticated successfully for user {user_id} connecting to device {device_id}")
            
            # Accept the WebSocket connection
            await websocket.accept()
            user_connections[device_id].append(websocket)
            
            # Request full sync from device when user connects
            if device_id in device_connections:
                try:
                    await device_connections[device_id].send_json({"type": "request_refresh"})
                    print(f"Sent refresh request to device {device_id} for new user connection")
                except:
                    pass
            
            try:
                while True:
                    data = await websocket.receive_json()
                    # Relay command to device
                    if device_id in device_connections:
                        await device_connections[device_id].send_json(data)
                    else:
                        await websocket.send_json({"error": "Device offline"})
            except WebSocketDisconnect:
                user_connections[device_id].remove(websocket)
                print(f"User disconnected from device {device_id}")
                
    except Exception as e:
        print(f"WebSocket authentication error for device {device_id}: {e}")
        import traceback
        traceback.print_exc()
        await websocket.close(code=1008, reason=str(e))
        return

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return templates.TemplateResponse("unauthorized.html", {"request": request}, status_code=401)
    if exc.status_code == 400 and exc.detail == "LOGIN_BAD_CREDENTIALS":
        return templates.TemplateResponse("suspended.html", {"request": request}, status_code=400)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.on_event("startup")
async def on_startup():
    # Initialize database schema (add missing columns if needed)
    from .init_database import init_database
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=9000, reload=True)