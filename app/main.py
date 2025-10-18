# app/main.py - Full app with FastAPI-Users (async SQLAlchemy)
from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean, select
from typing import List, Optional, Generator
from fastapi_users import FastAPIUsers, BaseUserManager, IntegerIDMixin
from fastapi_users.authentication import CookieTransport, AuthenticationBackend, JWTStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi.security import OAuth2AuthorizationCodeBearer
from httpx_oauth.clients.google import GoogleOAuth2
from fastapi_users import schemas
from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL").replace("mariadb+mariadbconnector", "mariadb+aiomysql")  # Use aiomysql for async MariaDB
SECRET = os.getenv("SECRET_KEY") or "secret"
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI") or "http://garden.ruvolo.loseyourip.com/auth/google/callback"

engine = create_async_engine(DATABASE_URL)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True)
    hashed_password = Column(String(1024))
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)  # For admin
    is_verified = Column(Boolean, default=False)

async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

class UserRead(schemas.BaseUser[int]):
    pass

class UserCreate(schemas.BaseUserCreate):
    is_active: Optional[bool] = True
    is_superuser: Optional[bool] = False
    is_verified: Optional[bool] = False

class UserLogin(BaseModel):
    username: str
    password: str

class UserManager(IntegerIDMixin, BaseUserManager[User, int]):
    reset_password_token_secret = SECRET
    verification_token_secret = SECRET

    async def on_after_register(self, user: User, request: None = None):
        print(f"User {user.id} has registered.")

async def get_db() -> Generator[AsyncSession, None, None]:
    async with async_session_maker() as session:
        yield session

async def get_user_db(db: AsyncSession = Depends(get_db)):
    yield SQLAlchemyUserDatabase(db, User)

async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)

cookie_transport = CookieTransport(cookie_max_age=3600)

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
async def admin_login(username: str = Form(...), password: str = Form(...), user_manager: UserManager = Depends(get_user_manager)):
    credentials = UserLogin(username=username, password=password)
    user = await user_manager.authenticate(credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    response = HTMLResponse(content="Logged in successfully! Go to <a href='/users'>Users Page</a>", status_code=200)
    await auth_backend.login(response, user)
    return response

# Google OAuth
google_oauth = GoogleOAuth2(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)

app.include_router(
    fastapi_users.get_oauth_router(
        google_oauth,
        auth_backend,
        SECRET,
        redirect_url=GOOGLE_REDIRECT_URI,
    ),
    prefix="/auth/google",
    tags=["auth"],
)

# New login landing page
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# Users page
@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, user: User = Depends(current_user)):
    return templates.TemplateResponse("users.html", {"request": request, "user": user})

# Admin: List users
@app.get("/admin/users", response_model=List[UserRead])
async def list_users(session: AsyncSession = Depends(get_db), admin: User = Depends(current_admin)):
    result = await session.execute(select(User))
    return result.scalars().all()

# Admin: Create user
@app.post("/admin/users", response_model=UserRead)
async def create_user_admin(user_create: UserCreate, admin: User = Depends(current_admin), manager: UserManager = Depends(get_user_manager)):
    user = await manager.create(user_create)
    return user

# Admin: Delete user
@app.delete("/admin/users/{user_id}")
async def delete_user_admin(user_id: int, session: AsyncSession = Depends(get_db), admin: User = Depends(current_admin)):
    user = await session.get(User, user_id)
    if user:
        await session.delete(user)
        await session.commit()
        return {"status": "success"}
    raise HTTPException(404, "User not found")

@app.on_event("startup")
async def on_startup():
    await create_db_and_tables()
    async with async_session_maker() as session:
        result = await session.execute(select(User).where(User.email == os.getenv("ADMIN_USERNAME")))
        admin = result.scalars().first()
        if not admin:
            admin_create = UserCreate(
                email=os.getenv("ADMIN_USERNAME"),
                password=os.getenv("ADMIN_PASSWORD"),
                is_superuser=True,
                is_active=True,
                is_verified=True
            )
            user_db = SQLAlchemyUserDatabase(session, User)
            manager = UserManager(user_db)
            await manager.create(admin_create)
            await session.commit()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=9000, reload=True)