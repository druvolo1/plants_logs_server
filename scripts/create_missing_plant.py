#!/usr/bin/env python3
"""
Script to create a missing plant in the database.
"""

import sys
import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(env_path)

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, Column, Integer, String, Boolean, DateTime, Float, ForeignKey
from sqlalchemy.orm import declarative_base

# Load database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("mariadb+mariadbconnector", "mariadb+aiomysql")

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)

class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(36), unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))

class Plant(Base):
    __tablename__ = "plants"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    system_id = Column(String(255), nullable=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    yield_grams = Column(Float, nullable=True)


async def create_plant(plant_id: str, device_id_str: str, plant_name: str, start_date_str: str, execute: bool = False):
    """Create a plant in the database."""

    if not DATABASE_URL:
        print("❌ DATABASE_URL not found in environment variables")
        return False

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Check if plant already exists
        result = await session.execute(select(Plant).where(Plant.plant_id == plant_id))
        existing_plant = result.scalars().first()

        if existing_plant:
            print(f"✅ Plant with ID {plant_id} already exists!")
            print(f"   Name: {existing_plant.name}")
            print(f"   Start Date: {existing_plant.start_date}")
            return True

        # Find the device
        result = await session.execute(select(Device).where(Device.device_id == device_id_str))
        device = result.scalars().first()

        if not device:
            print(f"❌ Device with device_id '{device_id_str}' not found")
            return False

        # Get user info
        result = await session.execute(select(User).where(User.id == device.user_id))
        user = result.scalars().first()

        print(f"\n📋 Plant to create:")
        print(f"   Plant ID: {plant_id}")
        print(f"   Name: {plant_name}")
        print(f"   Start Date: {start_date_str}")
        print(f"   Device ID: {device_id_str}")
        print(f"   User: {user.email if user else 'Unknown'}")

        if execute:
            # Parse start date
            try:
                start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
            except:
                # Try parsing as date only
                try:
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                except:
                    print(f"❌ Invalid date format: {start_date_str}")
                    print("   Expected formats: YYYY-MM-DD or ISO datetime")
                    return False

            # Create plant
            new_plant = Plant(
                plant_id=plant_id,
                name=plant_name,
                system_id=None,
                device_id=device.id,
                user_id=device.user_id,
                start_date=start_date,
                end_date=None,
                yield_grams=None
            )

            session.add(new_plant)
            await session.commit()

            print(f"\n✅ Plant created successfully!")
            return True
        else:
            print(f"\n⚠️  DRY RUN MODE - No changes made")
            print(f"   To create this plant, run with --execute flag")
            return False


def main():
    if len(sys.argv) < 5:
        print("Usage: python create_missing_plant.py <plant_id> <device_id> <plant_name> <start_date> [--execute]")
        print()
        print("Example:")
        print("  python create_missing_plant.py 1761617795751274 6072daae-2e9a-4798-99a7-6fb9feb80d7a \"Permanent Marker\" \"2025-08-15\" --execute")
        sys.exit(1)

    plant_id = sys.argv[1]
    device_id_str = sys.argv[2]
    plant_name = sys.argv[3]
    start_date_str = sys.argv[4]
    execute = "--execute" in sys.argv

    asyncio.run(create_plant(plant_id, device_id_str, plant_name, start_date_str, execute))


if __name__ == "__main__":
    main()
