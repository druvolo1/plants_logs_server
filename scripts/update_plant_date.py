#!/usr/bin/env python3
"""
Script to view and update a plant's start date.
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
from sqlalchemy import select, Column, Integer, String, ForeignKey, DateTime, Float
from sqlalchemy.orm import declarative_base

# Load database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("mariadb+mariadbconnector", "mariadb+aiomysql")

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255))

class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True)
    device_id = Column(String(36))

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


async def view_plant(plant_id: str):
    """View a plant's details."""

    if not DATABASE_URL:
        print("❌ DATABASE_URL not found in environment variables")
        return False

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Get plant
        result = await session.execute(select(Plant).where(Plant.plant_id == plant_id))
        plant = result.scalars().first()

        if not plant:
            print(f"❌ Plant with plant_id '{plant_id}' not found")
            return False

        print(f"\n🌱 Plant Details:")
        print(f"   Name: {plant.name}")
        print(f"   Plant ID: {plant.plant_id}")
        print(f"   Start Date: {plant.start_date}")
        print(f"   End Date: {plant.end_date}")
        print(f"   Yield: {plant.yield_grams}g" if plant.yield_grams else "   Yield: Not set")
        print()

        return True


async def update_plant_date(plant_id: str, new_start_date: str, execute: bool = False):
    """Update a plant's start date."""

    if not DATABASE_URL:
        print("❌ DATABASE_URL not found in environment variables")
        return False

    # Parse the new start date
    try:
        new_date = datetime.strptime(new_start_date, "%Y-%m-%d")
    except ValueError:
        print(f"❌ Invalid date format. Use YYYY-MM-DD (e.g., 2025-08-15)")
        return False

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Get plant
        result = await session.execute(select(Plant).where(Plant.plant_id == plant_id))
        plant = result.scalars().first()

        if not plant:
            print(f"❌ Plant with plant_id '{plant_id}' not found")
            return False

        print(f"\n🌱 Plant: {plant.name}")
        print(f"   Current start date: {plant.start_date}")
        print(f"   New start date: {new_date}")
        print()

        if execute:
            plant.start_date = new_date
            await session.commit()
            print(f"✅ Successfully updated start date to {new_date.strftime('%Y-%m-%d')}")
            return True
        else:
            print(f"⚠️  DRY RUN MODE - No changes made")
            print(f"   To execute this update, run with --execute flag")
            return False


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  View plant details:")
        print("    python update_plant_date.py <plant_id>")
        print()
        print("  Update plant start date:")
        print("    python update_plant_date.py <plant_id> <new_start_date> [--execute]")
        print()
        print("Examples:")
        print("  python update_plant_date.py 1761617795751274")
        print("  python update_plant_date.py 1761617795751274 2025-08-15")
        print("  python update_plant_date.py 1761617795751274 2025-08-15 --execute")
        sys.exit(1)

    plant_id = sys.argv[1]

    # If only plant_id provided, just view the plant
    if len(sys.argv) == 2:
        asyncio.run(view_plant(plant_id))
    else:
        new_start_date = sys.argv[2]
        execute = "--execute" in sys.argv
        asyncio.run(update_plant_date(plant_id, new_start_date, execute))


if __name__ == "__main__":
    main()
