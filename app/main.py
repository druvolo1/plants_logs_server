# app/main.py - Full app with FastAPI-Users (async SQLAlchemy)
from fastapi import FastAPI, Depends, HTTPException, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean, select, ForeignKey, DateTime
from sqlalchemy.orm import relationship, selectinload, Session
from datetime import datetime, timedelta
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
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="devices")

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

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None

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

    async def on_after_register(self, user: User, request: None = None):
        if user.is_active:
            print(f"User {user.id} has registered and been auto-approved (OAuth).")
        else:
            print(f"User {user.id} has registered and is pending approval.")

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
        
        # Check if user is pending approval
        if not user.is_active:
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
        except exceptions.UserNotExists:
            user = None
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

                        for existing_oauth_account in user.oauth_accounts:
                            if existing_oauth_account.oauth_name == oauth_name:
                                raise exceptions.UserAlreadyHasAccount()

                        user = await self.user_db.add_oauth_account(user, oauth_account_dict)
                except exceptions.UserNotExists:
                    pass

            if not user:
                # Google OAuth users are auto-approved
                # Generate a random secure password (OAuth users won't use it)
                random_password = secrets.token_urlsafe(32)
                user_create = UserCreate(
                    email=account_email,
                    password=random_password,  # Random password for OAuth users (not used)
                    is_verified=is_verified_by_default,
                    is_active=True  # Auto-approve Google users
                )
                user = await self.create(user_create)
                user = await self.user_db.add_oauth_account(user, oauth_account_dict)

        # Check if user is pending approval or suspended
        if not user.is_active:
            raise HTTPException(
                status_code=403,
                detail="PENDING_APPROVAL"
            )
        if user.is_suspended:
            raise HTTPException(
                status_code=403,
                detail="SUSPENDED"
            )

        return user

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

current_user = fastapi_users.current_user(active=True)
current_admin = fastapi_users.current_user(active=True, superuser=True)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Auth routes - We have custom registration, so don't include the register router
# app.include_router(
#     fastapi_users.get_register_router(UserRead, UserCreate),
#     prefix="/auth",
#     tags=["auth"],
# )

# OAuth router
app.include_router(
    fastapi_users.get_oauth_router(google_oauth_client, auth_backend, SECRET, associate_by_email=True),
    prefix="/auth/google",
    tags=["auth"],
)

# Middleware to intercept OAuth callback and return success page or handle errors
@app.middleware("http")
async def oauth_redirect_middleware(request: Request, call_next):
    try:
        response = await call_next(request)

        # If this is the OAuth callback and it returns 204, return a success page that redirects
        if request.url.path == "/auth/google/callback" and response.status_code == 204:
            # Return an HTML page that will redirect client-side
            # This preserves the cookie that was set
            html_content = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Login Successful</title>
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                    .spinner { border: 4px solid #f3f3f3; border-top: 4px solid #3498db;
                               border-radius: 50%; width: 40px; height: 40px;
                               animation: spin 1s linear infinite; margin: 20px auto; }
                    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
                </style>
            </head>
            <body>
                <h1>Login Successful!</h1>
                <div class="spinner"></div>
                <p>Redirecting...</p>
                <script>
                    setTimeout(function() {
                        window.location.href = '/';
                    }, 500);
                </script>
            </body>
            </html>
            """

            from fastapi.responses import HTMLResponse
            html_response = HTMLResponse(content=html_content, status_code=200)

            # Copy cookies from original OAuth response
            if hasattr(response, 'headers'):
                for key, value in response.headers.items():
                    if key.lower() == 'set-cookie':
                        html_response.headers.append(key, value)

            if hasattr(response, 'raw_headers'):
                for header_name, header_value in response.raw_headers:
                    if header_name == b'set-cookie':
                        html_response.raw_headers.append((header_name, header_value))

            return html_response

        return response
    except HTTPException as e:
        # Handle OAuth callback errors (pending approval or suspended)
        if request.url.path == "/auth/google/callback":
            if e.detail == "PENDING_APPROVAL":
                return templates.TemplateResponse("pending_approval.html", {"request": request})
            elif e.detail == "SUSPENDED":
                return templates.TemplateResponse("suspended.html", {"request": request})
        raise

@app.get("/auth/google/authorize", response_model=dict)
async def google_authorize(request: Request):
    redirect_uri = request.url_for("auth:google.callback")
    return await google_oauth_client.get_authorization_url(
        str(redirect_uri),
        state=None,
        scope=["openid", "email", "profile"]
    )

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
                
                if user and user.is_active:
                    # Redirect based on user type
                    if user.is_superuser:
                        return RedirectResponse("/dashboard")
                    else:
                        return RedirectResponse("/dashboard")
    except:
        pass
    
    # If anything fails, go to login
    return RedirectResponse("/login")

# Root redirect to login
@app.get("/")
async def root():
    return RedirectResponse(url="/login")

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
            is_verified=False
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

# Dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})

# Devices page
@app.get("/devices", response_class=HTMLResponse)
async def devices_page(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse("devices.html", {"request": request, "user": user})

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
    update_dict = {"is_active": False}
    user = await manager.user_db.update(user, update_dict)
    return {"status": "success"}

# Admin: Unsuspend user
@app.post("/admin/users/{user_id}/unsuspend")
async def unsuspend_user(user_id: int, admin: User = Depends(current_admin), manager: CustomUserManager = Depends(get_user_manager)):
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
        devices_list.append(DeviceRead(
            device_id=device.device_id,
            name=device.name,
            is_online=device.is_online,
            is_owner=True,
            permission_level=None,
            shared_by_email=None
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
        devices_list.append(DeviceRead(
            device_id=device.device_id,
            name=device.name,
            is_online=device.is_online,
            is_owner=False,
            permission_level=share.permission_level,
            shared_by_email=owner_email
        ))

    return devices_list

# Added: Delete device
@app.delete("/user/devices/{device_id}")
async def delete_device(device_id: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Device).where(Device.device_id == device_id, Device.user_id == user.id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(404, "Device not found")
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

# Added: Global connections for WS relay
device_connections: Dict[str, WebSocket] = {}
user_connections: Dict[str, List[WebSocket]] = defaultdict(list)

# Added: Device WS endpoint (for Pi)
@app.websocket("/ws/devices/{device_id}")
async def device_websocket(websocket: WebSocket, device_id: str, api_key: str = Query(...), session: AsyncSession = Depends(get_db)):
    await websocket.accept()
    print(f"Device connected: {device_id} with api_key {api_key}")  # Log connection accept
    result = await session.execute(select(Device).where(Device.device_id == device_id, Device.api_key == api_key))
    if not result.scalars().first():
        print(f"Invalid device/auth for {device_id}")  # Log invalid auth
        await websocket.close()
        return
    await session.execute(update(Device).where(Device.device_id == device_id).values(is_online=True))
    await session.commit()
    print(f"Set {device_id} online in DB")  # Log DB update
    device_connections[device_id] = websocket

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