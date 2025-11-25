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

# Added for WS
from fastapi import WebSocket, Query
from starlette.websockets import WebSocketDisconnect
from starlette.responses import RedirectResponse
from collections import defaultdict
import json
from sqlalchemy import update

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

engine = create_async_engine(DATABASE_URL)

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
    LogEntry,
    EnvironmentLog,
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
    LogEntryCreate,
    LogEntryRead,
    EnvironmentDataCreate,
    EnvironmentLogRead,
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
from app.routers import templates_router, locations_router, admin_router, logs_router, plants_router, plants_api_router, devices_router, devices_api_router
app.include_router(templates_router)
app.include_router(locations_router)
app.include_router(admin_router)
app.include_router(logs_router)
app.include_router(plants_router)
app.include_router(plants_api_router)
app.include_router(devices_router)
app.include_router(devices_api_router)

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

# Temporary storage for pending device pairings (device_id -> device_info)
# This avoids sessionStorage issues when redirecting to login
pending_pairings = {}

# Device pairing initiation (no auth required - stores params server-side)
@app.get("/pair-device", response_class=HTMLResponse)
async def device_pair_initiation(request: Request):
    """Device pairing initiation - stores device info server-side and shows login or pairing page"""
    # Get device info from query params
    device_id = request.query_params.get('device_id')
    device_name = request.query_params.get('name', 'Environment Sensor')
    mac_address = request.query_params.get('mac')
    model = request.query_params.get('model', 'HNENVCO2')
    manufacturer = request.query_params.get('manufacturer', 'HerbNerdz')
    sw_version = request.query_params.get('sw_version', '2.0')
    hw_version = request.query_params.get('hw_version', '1')

    if not device_id or not mac_address:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Invalid pairing request - missing device information"
        })

    # Store device info server-side with timestamp for cleanup
    pending_pairings[device_id] = {
        "device_id": device_id,
        "device_name": device_name,
        "mac_address": mac_address,
        "model": model,
        "manufacturer": manufacturer,
        "sw_version": sw_version,
        "hw_version": hw_version,
        "timestamp": datetime.utcnow()
    }

    # Check if user is already authenticated
    try:
        auth_cookie = request.cookies.get("auth_cookie")
        if auth_cookie:
            try:
                user = await current_user(request)
                # User is authenticated - show pairing page directly
                return templates.TemplateResponse("device_pair.html", {
                    "request": request,
                    "user": user,
                    "device_info": pending_pairings[device_id]
                })
            except:
                pass
    except:
        pass

    # Not authenticated - redirect to login with device_id in URL
    return RedirectResponse(url=f"/login?next=/pair-device-auth&device_id={device_id}", status_code=302)

# Device pairing page (requires authentication)
@app.get("/pair-device-auth", response_class=HTMLResponse)
async def device_pair_page(request: Request, user: User = Depends(current_user)):
    """Device pairing page for environment sensors - requires authentication"""
    device_id = request.query_params.get('device_id')

    # Get device info from server storage
    if not device_id or device_id not in pending_pairings:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Device pairing session expired or not found. Please start the pairing process again from your sensor."
        })

    device_info = pending_pairings[device_id]

    # Create a copy of device_info without the timestamp (not JSON serializable)
    device_info_for_template = {k: v for k, v in device_info.items() if k != 'timestamp'}

    return templates.TemplateResponse("device_pair.html", {
        "request": request,
        "user": user,
        "device_info": device_info_for_template
    })

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
    next: str = Form(None),
    device_id: str = Form(None),
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

        # Redirect based on next parameter if present, otherwise dashboard
        redirect_url = "/dashboard"
        if next and device_id:
            redirect_url = f"{next}?device_id={device_id}"
        elif next:
            redirect_url = next

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

# Locations page
@app.get("/locations", response_class=HTMLResponse)
async def locations_page(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse("locations.html", {"request": request, "user": user})

# Templates page
@app.get("/templates", response_class=HTMLResponse)
async def templates_page(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse("templates.html", {"request": request, "user": user})

# Admin endpoints moved to app/routers/admin.py
# Device endpoints moved to app/routers/devices.py
# Plant endpoints moved to app/routers/plants.py
# Log endpoints moved to app/routers/logs.py


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

    await session.execute(update(Device).where(Device.device_id == device_id).values(is_online=True, last_seen=datetime.utcnow()))
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

            # Handle device_info message for auto-detection
            if data.get('type') == 'device_info':
                device_type = data.get('device_type')
                capabilities = data.get('capabilities')

                updates = {}

                # Auto-detect device type
                if device_type:
                    updates['device_type'] = device_type
                    # Set scope based on device type
                    if device_type == 'environmental':
                        updates['scope'] = 'room'
                    else:
                        updates['scope'] = 'plant'
                    print(f"Auto-detected device type for {device_id}: {device_type}")

                # Store capabilities as JSON string
                if capabilities:
                    updates['capabilities'] = json.dumps(capabilities)
                    print(f"Stored capabilities for {device_id}: {capabilities}")

                # Update device in database
                if updates:
                    await session.execute(
                        update(Device)
                        .where(Device.device_id == device_id)
                        .values(**updates)
                    )
                    await session.commit()
                    print(f"Updated device {device_id} with: {updates}")

            # Extract and save system_name if present in the payload
            if data.get('type') == 'full_sync' or 'data' in data:
                payload = data.get('data', data)
                if 'settings' in payload:
                    system_name = payload['settings'].get('system_name')
                    if system_name and device.system_name != system_name:
                        await session.execute(
                            update(Device)
                            .where(Device.device_id == device_id)
                            .values(system_name=system_name)
                        )
                        await session.commit()
                        device.system_name = system_name
                        print(f"Updated system_name for {device_id}: {system_name}")

            # Relay to connected users
            for user_ws in user_connections[device_id]:
                await user_ws.send_json(data)
                print(f"Relayed to user for {device_id}: {json.dumps(data)}")  # Log relay
    except WebSocketDisconnect:
        print(f"Device disconnected: {device_id}")  # Log disconnect
        if device_id in device_connections:
            del device_connections[device_id]
        await session.execute(update(Device).where(Device.device_id == device_id).values(is_online=False, last_seen=datetime.utcnow()))
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

                # If not directly shared, check if device is in a location shared with user
                if not share and device.location_id:
                    result = await session.execute(
                        select(LocationShare).where(
                            LocationShare.location_id == device.location_id,
                            LocationShare.shared_with_user_id == user.id,
                            LocationShare.is_active == True,
                            LocationShare.revoked_at == None,
                            LocationShare.accepted_at != None,
                            or_(LocationShare.expires_at == None, LocationShare.expires_at > datetime.utcnow())
                        )
                    )
                    location_share = result.scalars().first()
                    if not location_share:
                        print(f"WebSocket auth failed: Device {device_id} not owned, shared, or in shared location with user {user_id}")
                        await websocket.close(code=1008, reason="Access denied")
                        return
                elif not share:
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=9000, reload=True)