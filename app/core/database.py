"""Database configuration and session management."""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
from .config import DATABASE_URL

engine = create_async_engine(DATABASE_URL)

class AsyncSessionGreenlet(AsyncSession):
    """Custom async session class for greenlet compatibility."""
    def __init__(self, *args, **kwargs):
        super().__init__(sync_session_class=Session, *args, **kwargs)

async_session_maker = async_sessionmaker(engine, class_=AsyncSessionGreenlet, expire_on_commit=False)
Base = declarative_base()

async def get_async_session():
    """Dependency to get async database session."""
    async with async_session_maker() as session:
        yield session

async def create_db_and_tables():
    """Create all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
