#!/usr/bin/env python3
"""
Script to list all plants in the database.
"""

import sys
import os
import asyncio
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(env_path)

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, Column, Integer, String, ForeignKey, DateTime, Float
from sqlalchemy.orm import declarative_base

# Load database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("mariadb+mariadbconnector", "mariadb+aiomysql")

Base = declarative_base()

class Plant(Base):
    __tablename__ = "plants"
    id = Column(Integer, primary_key=True)
    plant_id = Column(String(64), unique=True)
    name = Column(String(255))
    system_id = Column(String(255))
    device_id = Column(Integer, ForeignKey("devices.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    yield_grams = Column(Float)


async def list_all_plants():
    """List all plants in the database."""

    if not DATABASE_URL:
        print("❌ DATABASE_URL not found in environment variables")
        return False

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Get all plants
        result = await session.execute(select(Plant))
        plants = result.scalars().all()

        if not plants:
            print("❌ No plants found in database")
            return False

        print(f"\n🌱 Found {len(plants)} plant(s):\n")
        for plant in plants:
            print(f"   Name: {plant.name}")
            print(f"   Plant ID: {plant.plant_id}")
            print(f"   Database ID: {plant.id}")
            print(f"   Device ID: {plant.device_id}")
            print(f"   User ID: {plant.user_id}")
            print(f"   Start Date: {plant.start_date}")
            print(f"   End Date: {plant.end_date}")
            print(f"   Yield: {plant.yield_grams}g" if plant.yield_grams else "   Yield: Not set")
            print()

        return True


if __name__ == "__main__":
    asyncio.run(list_all_plants())
