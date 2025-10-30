#!/usr/bin/env python3
"""
Script to remove duplicate log entries from the database.
Keeps the first occurrence of each duplicate based on timestamp.
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
from sqlalchemy import select, Column, Integer, String, ForeignKey, DateTime, Float, delete
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

class LogEntry(Base):
    __tablename__ = "log_entries"
    id = Column(Integer, primary_key=True)
    plant_id = Column(Integer, ForeignKey("plants.id"))
    event_type = Column(String(50))
    sensor_name = Column(String(50))
    value = Column(Float)
    dose_type = Column(String(50))
    dose_amount_ml = Column(Float)
    timestamp = Column(DateTime)


async def remove_duplicates(plant_id: str = None, execute: bool = False):
    """Remove duplicate log entries."""

    if not DATABASE_URL:
        print("❌ DATABASE_URL not found in environment variables")
        return False

    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Get plant if plant_id specified
        plant_filter = None
        if plant_id:
            result = await session.execute(select(Plant).where(Plant.plant_id == plant_id))
            plant = result.scalars().first()
            if not plant:
                print(f"❌ Plant with plant_id '{plant_id}' not found")
                return False
            plant_filter = plant.id
            print(f"\n🌱 Processing plant: {plant.name} (ID: {plant.plant_id})")
        else:
            print(f"\n🌱 Processing ALL plants")

        # Get all log entries for the plant(s)
        query = select(LogEntry).order_by(LogEntry.plant_id, LogEntry.timestamp, LogEntry.event_type, LogEntry.id)
        if plant_filter:
            query = query.where(LogEntry.plant_id == plant_filter)

        result = await session.execute(query)
        all_logs = result.scalars().all()

        print(f"📊 Total log entries: {len(all_logs)}")

        # Find duplicates
        seen = {}
        duplicates_to_delete = []

        for log in all_logs:
            # Create a key based on plant_id, timestamp, and event_type
            key = (log.plant_id, log.timestamp, log.event_type)

            if key in seen:
                # This is a duplicate - mark for deletion
                duplicates_to_delete.append(log.id)
            else:
                # First occurrence - keep it
                seen[key] = log.id

        print(f"🔍 Found {len(duplicates_to_delete)} duplicate entries")

        if len(duplicates_to_delete) == 0:
            print("✅ No duplicates found!")
            return True

        if execute:
            print(f"\n🗑️  Deleting {len(duplicates_to_delete)} duplicate entries...")

            # Delete duplicates in batches
            batch_size = 100
            deleted_count = 0
            for i in range(0, len(duplicates_to_delete), batch_size):
                batch = duplicates_to_delete[i:i+batch_size]
                await session.execute(
                    delete(LogEntry).where(LogEntry.id.in_(batch))
                )
                deleted_count += len(batch)
                print(f"  Deleted {deleted_count}/{len(duplicates_to_delete)}...")

            await session.commit()
            print(f"✅ Successfully deleted {len(duplicates_to_delete)} duplicate entries!")
            return True
        else:
            print(f"\n⚠️  DRY RUN MODE - No changes made")
            print(f"   {len(duplicates_to_delete)} duplicates would be deleted")
            print(f"   To execute this deletion, run with --execute flag")
            return False


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Remove duplicates for specific plant:")
        print("    python remove_duplicate_logs.py <plant_id> [--execute]")
        print()
        print("  Remove duplicates for ALL plants:")
        print("    python remove_duplicate_logs.py --all [--execute]")
        print()
        print("Examples:")
        print("  python remove_duplicate_logs.py 1761617795751274")
        print("  python remove_duplicate_logs.py 1761617795751274 --execute")
        print("  python remove_duplicate_logs.py --all --execute")
        sys.exit(1)

    if sys.argv[1] == "--all":
        plant_id = None
    else:
        plant_id = sys.argv[1]

    execute = "--execute" in sys.argv

    asyncio.run(remove_duplicates(plant_id, execute))


if __name__ == "__main__":
    main()
