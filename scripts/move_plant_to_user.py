#!/usr/bin/env python3
"""
Script to move a plant from one device/user to another.
Usage: python move_plant_to_user.py <plant_id> <target_device_id> [--execute]
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
from sqlalchemy import select, Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship

# Load database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("mariadb+mariadbconnector", "mariadb+aiomysql")

# Define models directly to avoid importing main.py which initializes the FastAPI app
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_superuser = Column(Boolean, default=False)

class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(36), unique=True, index=True)
    api_key = Column(String(64))
    name = Column(String(255), nullable=True)
    is_online = Column(Boolean, default=False)
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

class LogEntry(Base):
    __tablename__ = "log_entries"
    id = Column(Integer, primary_key=True, index=True)
    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    sensor_name = Column(String(50))
    value = Column(Float)
    dose_type = Column(String(50))
    dose_amount_ml = Column(Float)
    timestamp = Column(DateTime, nullable=False, index=True)


async def move_plant(plant_id: str, target_device_id: str, execute: bool = False):
    """Move a plant to a different device."""

    if not DATABASE_URL:
        print("❌ DATABASE_URL not found in environment variables")
        return False

    # Create database engine
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Find the plant
        result = await session.execute(select(Plant).where(Plant.plant_id == plant_id))
        plant = result.scalars().first()

        if not plant:
            print(f"❌ Plant with plant_id '{plant_id}' not found in database")
            return False

        # Get current device info
        result = await session.execute(select(Device).where(Device.id == plant.device_id))
        current_device = result.scalars().first()

        if not current_device:
            print(f"⚠️  Plant exists but has no current device (device.id={plant.device_id})")
        else:
            result = await session.execute(select(User).where(User.id == current_device.user_id))
            current_user = result.scalars().first()
            print(f"\n📍 Current ownership:")
            print(f"   Plant: {plant.name} (ID: {plant.plant_id})")
            print(f"   Device: {current_device.name} (ID: {current_device.device_id})")
            print(f"   User: {current_user.email if current_user else 'Unknown'}")

        # Find target device
        result = await session.execute(select(Device).where(Device.device_id == target_device_id))
        target_device = result.scalars().first()

        if not target_device:
            print(f"\n❌ Target device with device_id '{target_device_id}' not found")
            return False

        # Get target user info
        result = await session.execute(select(User).where(User.id == target_device.user_id))
        target_user = result.scalars().first()

        print(f"\n🎯 Target ownership:")
        print(f"   Device: {target_device.name} (ID: {target_device.device_id})")
        print(f"   User: {target_user.email if target_user else 'Unknown'}")

        # Count logs
        result = await session.execute(
            select(LogEntry).where(LogEntry.plant_id == plant.id)
        )
        logs = result.scalars().all()
        log_count = len(logs)

        print(f"\n📊 Plant has {log_count} log entries")

        if current_device and plant.device_id == target_device.id and plant.user_id == target_device.user_id:
            print(f"\n✅ Plant is already owned by the target device!")
            return True

        if execute:
            print(f"\n🔄 Moving plant to new device...")
            plant.device_id = target_device.id
            plant.user_id = target_device.user_id
            await session.commit()
            print(f"✅ Plant successfully moved!")
            print(f"   {plant.name} now belongs to device {target_device.name} (user: {target_user.email})")
            return True
        else:
            print(f"\n⚠️  DRY RUN MODE - No changes made")
            print(f"   To execute this change, run with --execute flag")
            return False


async def list_all_plants():
    """List all plants in the database with their owners."""

    if not DATABASE_URL:
        print("❌ DATABASE_URL not found in environment variables")
        return

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(select(Plant))
        plants = result.scalars().all()

        if not plants:
            print("No plants found in database")
            return

        print(f"\n{'='*80}")
        print(f"All Plants in Database:")
        print(f"{'='*80}\n")

        for plant in plants:
            result = await session.execute(select(Device).where(Device.id == plant.device_id))
            device = result.scalars().first()

            if device:
                result = await session.execute(select(User).where(User.id == device.user_id))
                user = result.scalars().first()
                user_email = user.email if user else "Unknown"
            else:
                device = None
                user_email = "No device"

            # Count logs
            result = await session.execute(
                select(LogEntry).where(LogEntry.plant_id == plant.id)
            )
            log_count = len(result.scalars().all())

            print(f"🌱 {plant.name}")
            print(f"   Plant ID: {plant.plant_id}")
            print(f"   Device: {device.name if device else 'None'} ({device.device_id if device else 'N/A'})")
            print(f"   User: {user_email}")
            print(f"   Logs: {log_count}")
            print(f"   Started: {plant.start_date}")
            print(f"   Status: {'Finished' if plant.end_date else 'Active'}")
            print()


async def list_all_devices():
    """List all devices in the database."""

    if not DATABASE_URL:
        print("❌ DATABASE_URL not found in environment variables")
        return

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(select(Device))
        devices = result.scalars().all()

        if not devices:
            print("No devices found in database")
            return

        print(f"\n{'='*80}")
        print(f"All Devices in Database:")
        print(f"{'='*80}\n")

        for device in devices:
            result = await session.execute(select(User).where(User.id == device.user_id))
            user = result.scalars().first()

            print(f"🖥️  {device.name or 'Unnamed Device'}")
            print(f"   Device ID: {device.device_id}")
            print(f"   User: {user.email if user else 'Unknown'}")
            print()


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  List all plants:  python move_plant_to_user.py --list-plants")
        print("  List all devices: python move_plant_to_user.py --list-devices")
        print("  Move plant:       python move_plant_to_user.py <plant_id> <target_device_id> [--execute]")
        print()
        print("Examples:")
        print("  python move_plant_to_user.py --list-plants")
        print("  python move_plant_to_user.py abc123 6072daae-2e9a-4798-99a7-6fb9feb80d7a")
        print("  python move_plant_to_user.py abc123 6072daae-2e9a-4798-99a7-6fb9feb80d7a --execute")
        sys.exit(1)

    if sys.argv[1] == "--list-plants":
        asyncio.run(list_all_plants())
    elif sys.argv[1] == "--list-devices":
        asyncio.run(list_all_devices())
    else:
        if len(sys.argv) < 3:
            print("Error: Both plant_id and target_device_id are required")
            print("Usage: python move_plant_to_user.py <plant_id> <target_device_id> [--execute]")
            sys.exit(1)

        plant_id = sys.argv[1]
        target_device_id = sys.argv[2]
        execute = "--execute" in sys.argv

        asyncio.run(move_plant(plant_id, target_device_id, execute))


if __name__ == "__main__":
    main()
