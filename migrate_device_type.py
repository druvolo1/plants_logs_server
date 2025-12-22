"""
Migration script to update device_type from monitoring_system to hydro_controller
"""
import asyncio
from sqlalchemy import text
from app.main import async_session_maker

async def migrate():
    async with async_session_maker() as session:
        # Update device_type
        result = await session.execute(
            text("UPDATE devices SET device_type = :new_type WHERE device_type = :old_type"),
            {"new_type": "hydro_controller", "old_type": "monitoring_system"}
        )
        await session.commit()
        print(f"✓ Updated {result.rowcount} devices from 'monitoring_system' to 'hydro_controller'")

if __name__ == "__main__":
    asyncio.run(migrate())
