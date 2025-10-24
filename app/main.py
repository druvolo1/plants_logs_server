# app/main.py - Full app with FastAPI-Users (async SQLAlchemy)
from fastapi import FastAPI, Depends, HTTPException, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean, select, ForeignKey
from sqlalchemy.orm import relationship, selectinload, Session
from typing import List, Optional, Generator, Any, Dict
from fastapi_users import FastAPIUsers, BaseUserManager, IntegerIDMixin
from fastapi_users.authentication import CookieTransport, AuthenticationBackend, JWTStrategy
from fastapi_users.authentication.strategy.db import AccessTokenDatabase, DatabaseStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi.security import OAuth2AuthorizationCodeBearer
from httpx_oauth.clients.google import GoogleOAuth2
from fastapi_users import schemas, exceptions
from pydantic import BaseModel
from dotenv import load_dotenv
import os

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
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)  # For admin
    is_verified = Column(Boolean, default=False)
    oauth_accounts = relationship("OAuthAccount", back_populates="user", cascade="all, delete-orphan")

async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

class UserRead(schemas.BaseUser[int]):
    pass

class UserCreate(schemas.BaseUserCreate):
    password: Optional[str] = None
    is_active: Optional[bool] = True
    is_superuser: Optional[bool] = False
    is_verified: Optional[bool] = False

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
        print(f"User {user.id} has registered.")

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
                user_create = UserCreate(email=account_email, is_verified=is_verified_by_default)
                user = await self.create(user_create)
                user = await self.user_db.add_oauth_account(user, oauth_account_dict)

        return user

    async def create(
        self,
        user_create: schemas.BaseUserCreate,
        safe: bool = False,
        is_verified: bool = False,
    ) -> User:
        await self.validate_password(user_create.password, user_create)

        existing_user = await self.user_db.get_by_email(user_create.email)
        if existing_user is not None:
            raise exceptions.UserAlreadyExists()

        user_dict = (
            user_create.create_update_dict()
            if safe
            else user_create.create_update_dict_superuser()
        )
        if user_create.password is None:
            user_dict["hashed_password"] = None
        else:
            password = user_create.password
            del user_dict["password"]
            user_dict["hashed_password"] = self.password_helper.hash(password)
        if is_verified:
            user_dict["is_verified"] = True

        created_user = await self.user_db.create(user_dict)

        await self.on_after_register(created_user, None)

        return created_user

    async def on_after_login(self, user: User, request: Optional[Request] = None, response: Optional[Response] = None) -> None:
        if response is not None:
            if user.is_superuser:
                response.headers["Location"] = "/users"
            else:
                response.headers["Location"] = "/dashboard"
            response.status_code = 303

async def get_db() -> Generator[AsyncSession, None, None]:
    async with async_session_maker() as session:
        yield session

async def get_user_db(db: AsyncSession = Depends(get_db)):
    yield CustomSQLAlchemyUserDatabase(db, User, oauth_account_table=OAuthAccount)

async def get_user_manager(user_db: CustomSQLAlchemyUserDatabase = Depends(get_user_db)):
    yield CustomUserManager(user_db)

cookie_transport = CookieTransport(cookie_max_age=3600, cookie_secure=False)

def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)

auth_backend = AuthenticationBackend(
    name="jwt",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, int](
    get_user_manager,
    [auth_backend],
)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

current_user = fastapi_users.current_user(active=True)
current_admin = fastapi_users.current_user(active=True, superuser=True)

# Routes for auth (excluding the default login to override it)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/auth",
    tags=["auth"],
)

app.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/auth",
    tags=["auth"],
)

# Custom admin login route to accept form data
@app.post("/auth/jwt/login")
async def admin_login(username: str = Form(...), password: str = Form(...), user_manager: CustomUserManager = Depends(get_user_manager)):
    print(f"Attempted login with username: {username} and password: {password}")
    credentials = UserLogin(username=username, password=password)
    user = await user_manager.authenticate(credentials)
    if not user:
        print("Authentication failed")
        return templates.TemplateResponse("login.html", {"request": Request, "error": "Invalid credentials"})
    print("Authentication successful")
    strategy = get_jwt_strategy()
    token = await strategy.write_token(user)
    if user.is_superuser:
        response = RedirectResponse(url="/users", status_code=303)
    else:
        response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key=cookie_transport.cookie_name,
        value=token,
        max_age=cookie_transport.cookie_max_age,
        httponly=True,
        secure=cookie_transport.cookie_secure,
        samesite=cookie_transport.cookie_samesite,
        domain=cookie_transport.cookie_domain,
    )
    return response

# Logout endpoint
@app.get("/auth/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie(cookie_transport.cookie_name)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Google OAuth
google_oauth = GoogleOAuth2(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)

app.include_router(
    fastapi_users.get_oauth_router(
        google_oauth,
        auth_backend,
        SECRET,
        redirect_url=None,
    ),
    prefix="/auth/google",
    tags=["auth"],
)

# New login landing page
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

# Users page
@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, admin: User = Depends(current_admin), session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(User))
    users = result.scalars().all()
    response = templates.TemplateResponse("users.html", {"request": request, "user": admin, "users": users})
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Dashboard page (for non-admins)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, user: User = Depends(current_user)):
    response = templates.TemplateResponse("dashboard.html", {"request": request, "user": user})
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Admin: List users
@app.get("/admin/users", response_model=List[UserRead])
async def list_users(session: AsyncSession = Depends(get_db), admin: User = Depends(current_admin)):
    result = await session.execute(select(User))
    return result.scalars().all()

# Admin: Create user
@app.post("/admin/users", response_model=UserRead)
async def create_user_admin(user_create: UserCreate, admin: User = Depends(current_admin), manager: CustomUserManager = Depends(get_user_manager)):
    user = await manager.create(user_create)
    return user

# Admin: Reset user password
@app.post("/admin/users/{user_id}/reset-password")
async def reset_user_password(user_id: int, password_reset: PasswordReset, admin: User = Depends(current_admin), manager: CustomUserManager = Depends(get_user_manager)):
    user = await manager.user_db.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    hashed_password = manager.password_helper.hash(password_reset.password)
    update_dict = {"hashed_password": hashed_password}
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

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return templates.TemplateResponse("unauthorized.html", {"request": request}, status_code=401)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.on_event("startup")
async def on_startup():
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