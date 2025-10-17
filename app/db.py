from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from fastapi_users.db import SQLAlchemyBaseUserTable, SQLAlchemyUserDatabase
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}?charset=utf8mb4"
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(SQLAlchemyBaseUserTable[int], Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(1024), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

class Plant(Base):
    __tablename__ = "plants"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))  # For data isolation
    created_at = Column(DateTime, default=datetime.utcnow)

class DosingLog(Base):
    __tablename__ = "dosing_logs"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"))
    event_type = Column(String(50))
    ph = Column(Float)
    dose_type = Column(String(10))
    dose_amount_ml = Column(Float)
    timestamp = Column(DateTime)

class FeedingLog(Base):
    __tablename__ = "feeding_logs"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"))
    event_type = Column(String(50))
    message = Column(Text)
    status = Column(String(50))
    timestamp = Column(DateTime)
    plant_ip = Column(String(255))

class PhLog(Base):
    __tablename__ = "ph_logs"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id"))
    event_type = Column(String(50))
    sensor_name = Column(String(50))
    value = Column(Float)
    timestamp = Column(DateTime)

Base.metadata.create_all(bind=engine)

async def get_user_db(session: Session = Depends(get_db)):
    yield SQLAlchemyUserDatabase(session, User)