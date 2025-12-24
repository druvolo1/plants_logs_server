import asyncio
from sqlalchemy import text
from app.main import engine

async def check():
    async with engine.begin() as conn:
        result = await conn.execute(text(
            "SELECT device_id, is_online, last_seen FROM devices WHERE device_type = 'hydroponic_controller'"
        ))
        rows = result.fetchall()
        print('Hydro controller in DB:')
        for row in rows:
            print(f'  device_id={row[0]}')
            print(f'  is_online={row[1]}')
            print(f'  last_seen={row[2]}')

asyncio.run(check())
