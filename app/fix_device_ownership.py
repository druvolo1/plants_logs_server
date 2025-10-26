#!/usr/bin/env python3
"""
Fix Device Ownership Script

This script reassigns all devices to the admin user.
Use this when devices exist in the database but aren't showing up for your user.

Usage:
    python fix_device_ownership.py
"""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, update, text
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("mariadb+mariadbconnector", "mariadb+aiomysql")

ADMIN_EMAIL = os.getenv("ADMIN_USERNAME")

async def fix_device_ownership():
    """Reassign all devices to the admin user."""
    print("\n" + "="*80)
    print("DEVICE OWNERSHIP FIX SCRIPT")
    print("="*80)
    
    if not DATABASE_URL:
        print("\n✗ ERROR: DATABASE_URL not found in environment variables\n")
        return False
    
    if not ADMIN_EMAIL:
        print("\n✗ ERROR: ADMIN_USERNAME not found in environment variables\n")
        return False
    
    print(f"\nAdmin email: {ADMIN_EMAIL}")
    print("Connecting to database...")
    
    try:
        engine = create_async_engine(DATABASE_URL)
        async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
        
        async with async_session_maker() as session:
            # Get admin user ID
            result = await session.execute(
                text("SELECT id FROM users WHERE email = :email"),
                {"email": ADMIN_EMAIL}
            )
            admin = result.fetchone()
            
            if not admin:
                print(f"\n✗ ERROR: Admin user '{ADMIN_EMAIL}' not found in database")
                print("  Please check your ADMIN_USERNAME in .env file\n")
                return False
            
            admin_id = admin[0]
            print(f"✓ Found admin user (ID: {admin_id})")
            
            # Get all devices
            result = await session.execute(
                text("SELECT device_id, name, user_id FROM devices")
            )
            devices = result.fetchall()
            
            if not devices:
                print("\n✓ No devices found in database")
                print("  You can now add devices from the /devices page\n")
                return True
            
            print(f"\nFound {len(devices)} device(s):")
            print("-" * 80)
            
            devices_to_fix = []
            for device in devices:
                device_id, name, user_id = device
                status = "✓ Already yours" if user_id == admin_id else "✗ Belongs to another user"
                print(f"  {name or device_id[:20]}... - {status}")
                if user_id != admin_id:
                    devices_to_fix.append(device_id)
            
            if not devices_to_fix:
                print("\n✓ All devices are already assigned to you!")
                print("  If they're not showing up, try restarting your browser or clearing cache\n")
                return True
            
            # Ask for confirmation
            print(f"\n⚠ Found {len(devices_to_fix)} device(s) that need to be reassigned")
            print(f"  These devices will be transferred to: {ADMIN_EMAIL}")
            
            confirm = input("\nDo you want to proceed? (yes/no): ").strip().lower()
            
            if confirm not in ['yes', 'y']:
                print("\n✗ Operation cancelled\n")
                return False
            
            # Reassign devices
            print("\nReassigning devices...")
            for device_id in devices_to_fix:
                await session.execute(
                    text("UPDATE devices SET user_id = :admin_id WHERE device_id = :device_id"),
                    {"admin_id": admin_id, "device_id": device_id}
                )
                print(f"  ✓ Reassigned device: {device_id[:20]}...")
            
            await session.commit()
            
            print("\n" + "="*80)
            print(f"✓ SUCCESS! Reassigned {len(devices_to_fix)} device(s) to {ADMIN_EMAIL}")
            print("="*80)
            print("\nNext steps:")
            print("  1. Refresh your browser")
            print("  2. Go to http://garden.ruvolo.loseyourip.com/devices")
            print("  3. Your devices should now appear!")
            print("  4. Go to http://garden.ruvolo.loseyourip.com/dashboard")
            print("  5. Your dashboard should now show your devices!\n")
            
            return True
            
        await engine.dispose()
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}\n")
        return False

async def list_all_users():
    """List all users in the database for troubleshooting."""
    print("\n" + "="*80)
    print("ALL USERS IN DATABASE")
    print("="*80)
    
    try:
        engine = create_async_engine(DATABASE_URL)
        async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
        
        async with async_session_maker() as session:
            result = await session.execute(
                text("SELECT id, email, is_superuser, is_active FROM users")
            )
            users = result.fetchall()
            
            if not users:
                print("\n✗ No users found in database\n")
                return
            
            print(f"\nFound {len(users)} user(s):")
            print("-" * 80)
            for user in users:
                user_id, email, is_superuser, is_active = user
                admin_badge = " [ADMIN]" if is_superuser else ""
                status = "Active" if is_active else "Pending"
                print(f"  ID: {user_id} | {email}{admin_badge} | {status}")
            print()
            
        await engine.dispose()
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}\n")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--list-users":
        asyncio.run(list_all_users())
    else:
        asyncio.run(fix_device_ownership())
