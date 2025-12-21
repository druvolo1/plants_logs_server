# app/routers/websocket.py
"""
WebSocket endpoints for device and user real-time communication.
"""
from typing import Dict, List
from datetime import datetime
from collections import defaultdict
import json

from fastapi import APIRouter, Depends, WebSocket, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, or_
from starlette.websockets import WebSocketDisconnect
import jwt

from app.models import User, Device, DeviceShare, LocationShare, DeviceFirmwareAssignment

router = APIRouter(tags=["websocket"])

# Global connections for WS relay
device_connections: Dict[str, WebSocket] = {}
user_connections: Dict[str, List[WebSocket]] = defaultdict(list)


def get_db_dependency():
    """Import and return get_db dependency"""
    from app.main import get_db
    return get_db


def get_secret():
    """Import and return SECRET"""
    from app.main import SECRET
    return SECRET


def get_async_session_maker():
    """Import and return async_session_maker"""
    from app.main import async_session_maker
    return async_session_maker


# Device WS endpoint (for Pi/ESP devices)
@router.websocket("/ws/devices/{device_id}")
async def device_websocket(
    websocket: WebSocket,
    device_id: str,
    api_key: str = Query(...),
    session: AsyncSession = Depends(get_db_dependency())
):
    await websocket.accept()
    print(f"Device connected: {device_id} with api_key {api_key}")

    # Get device and verify auth
    result = await session.execute(
        select(Device, User)
        .join(User, Device.user_id == User.id)
        .where(Device.device_id == device_id, Device.api_key == api_key)
    )
    row = result.first()
    if not row:
        print(f"Invalid device/auth for {device_id}")
        await websocket.close()
        return

    device, user = row

    await session.execute(update(Device).where(Device.device_id == device_id).values(is_online=True, last_seen=datetime.utcnow()))
    await session.commit()
    print(f"Set {device_id} online in DB")
    device_connections[device_id] = websocket

    # Send owner info to device
    try:
        await websocket.send_json({
            "command": "server_info",
            "owner_email": user.email,
            "owner_name": user.email.split('@')[0]
        })
        print(f"Sent owner info to device {device_id}: {user.email}")
    except Exception as e:
        print(f"Failed to send owner info to device {device_id}: {e}")

    # Notify all connected users that the device is online
    for user_ws in user_connections[device_id]:
        try:
            await user_ws.send_json({"type": "device_status", "online": True})
        except:
            pass  # User might have disconnected

    # Check for pending force firmware update (for ESP32 devices)
    if device.device_type in ['valve_controller', 'hydroponic_controller']:
        try:
            assignment_result = await session.execute(
                select(DeviceFirmwareAssignment).where(
                    DeviceFirmwareAssignment.device_id == device.id,
                    DeviceFirmwareAssignment.force_update == True
                )
            )
            pending_assignment = assignment_result.scalars().first()
            if pending_assignment:
                await websocket.send_json({"type": "firmware_update"})
                print(f"[FIRMWARE] Sent pending firmware_update command to {device_id} on connect")
        except Exception as e:
            print(f"[FIRMWARE] Error checking pending firmware update for {device_id}: {e}")

    try:
        while True:
            data = await websocket.receive_json()
            print(f"Received from device {device_id}: {json.dumps(data)}")

            # Handle device_info message for auto-detection
            if data.get('type') == 'device_info':
                device_type = data.get('device_type')
                capabilities = data.get('capabilities')

                updates = {}

                # Auto-detect device type
                if device_type:
                    updates['device_type'] = device_type
                    # Set scope based on device type
                    if device_type == 'environmental':
                        updates['scope'] = 'room'
                    else:
                        updates['scope'] = 'plant'
                    print(f"Auto-detected device type for {device_id}: {device_type}")

                # Store capabilities as JSON string
                if capabilities:
                    updates['capabilities'] = json.dumps(capabilities)
                    print(f"Stored capabilities for {device_id}: {capabilities}")

                # Update device in database
                if updates:
                    await session.execute(
                        update(Device)
                        .where(Device.device_id == device_id)
                        .values(**updates)
                    )
                    await session.commit()
                    print(f"Updated device {device_id} with: {updates}")

            # Extract and save system_name if present in the payload
            if data.get('type') == 'full_sync' or 'data' in data:
                payload = data.get('data', data)
                if 'settings' in payload:
                    system_name = payload['settings'].get('system_name')
                    if system_name and device.system_name != system_name:
                        await session.execute(
                            update(Device)
                            .where(Device.device_id == device_id)
                            .values(system_name=system_name)
                        )
                        await session.commit()
                        device.system_name = system_name
                        print(f"Updated system_name for {device_id}: {system_name}")

            # Relay to connected users
            for user_ws in user_connections[device_id]:
                await user_ws.send_json(data)
                print(f"Relayed to user for {device_id}: {json.dumps(data)}")
    except WebSocketDisconnect:
        print(f"Device disconnected cleanly: {device_id}")
    except Exception as e:
        print(f"Device connection error for {device_id}: {e}")
    finally:
        # Always clean up and mark device offline, regardless of how connection ended
        print(f"Cleaning up device connection: {device_id}")
        if device_id in device_connections:
            del device_connections[device_id]

        try:
            await session.execute(update(Device).where(Device.device_id == device_id).values(is_online=False, last_seen=datetime.utcnow()))
            await session.commit()
            print(f"Set {device_id} offline in DB")
        except Exception as db_error:
            print(f"Error setting {device_id} offline in DB: {db_error}")

        # Notify all connected users that the device went offline
        for user_ws in user_connections[device_id]:
            try:
                await user_ws.send_json({"error": "Device offline"})
            except:
                pass  # User might have already disconnected


# User WS endpoint (for web dashboard)
@router.websocket("/ws/user/devices/{device_id}")
async def user_websocket(websocket: WebSocket, device_id: str):
    # Manual authentication for WebSocket
    cookie = websocket.cookies.get("auth_cookie")

    if not cookie:
        print(f"WebSocket auth failed: No cookie for device {device_id}")
        await websocket.close(code=1008, reason="No authentication cookie")
        return

    # Get user from cookie
    try:
        async_session_maker = get_async_session_maker()
        SECRET = get_secret()

        async with async_session_maker() as session:
            # Decode the JWT token directly - ignore audience claim
            try:
                payload = jwt.decode(
                    cookie,
                    SECRET,
                    algorithms=["HS256"],
                    options={"verify_aud": False}
                )
                user_id = payload.get("sub")

                if not user_id:
                    print(f"WebSocket auth failed: No user_id in token for device {device_id}")
                    await websocket.close(code=1008, reason="Invalid token")
                    return

                # Parse user_id to int
                try:
                    user_id = int(user_id)
                except (ValueError, TypeError):
                    print(f"WebSocket auth failed: Invalid user_id format for device {device_id}")
                    await websocket.close(code=1008, reason="Invalid user ID")
                    return

            except jwt.ExpiredSignatureError:
                print(f"WebSocket auth failed: Expired token for device {device_id}")
                await websocket.close(code=1008, reason="Token expired")
                return
            except jwt.InvalidTokenError as e:
                print(f"WebSocket auth failed: Invalid token for device {device_id}: {e}")
                await websocket.close(code=1008, reason="Invalid token")
                return

            # Get user from database
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalars().first()

            if not user or not user.is_active:
                print(f"WebSocket auth failed: User not found or inactive for device {device_id}")
                await websocket.close(code=1008, reason="User not active")
                return

            # Check if user owns this device OR has it shared with them
            result = await session.execute(select(Device).where(Device.device_id == device_id, Device.user_id == user.id))
            device = result.scalars().first()

            # If not owner, check if device is shared with user
            if not device:
                # Get device first
                result = await session.execute(select(Device).where(Device.device_id == device_id))
                device = result.scalars().first()

                if not device:
                    print(f"WebSocket auth failed: Device {device_id} not found")
                    await websocket.close(code=1008, reason="Device not found")
                    return

                # Check if device is shared with this user
                result = await session.execute(
                    select(DeviceShare).where(
                        DeviceShare.device_id == device.id,
                        DeviceShare.shared_with_user_id == user.id,
                        DeviceShare.is_active == True,
                        DeviceShare.revoked_at == None,
                        DeviceShare.accepted_at != None
                    )
                )
                share = result.scalars().first()

                # If not directly shared, check if device is in a location shared with user
                if not share and device.location_id:
                    result = await session.execute(
                        select(LocationShare).where(
                            LocationShare.location_id == device.location_id,
                            LocationShare.shared_with_user_id == user.id,
                            LocationShare.is_active == True,
                            LocationShare.revoked_at == None,
                            LocationShare.accepted_at != None,
                            or_(LocationShare.expires_at == None, LocationShare.expires_at > datetime.utcnow())
                        )
                    )
                    location_share = result.scalars().first()
                    if not location_share:
                        print(f"WebSocket auth failed: Device {device_id} not owned, shared, or in shared location with user {user_id}")
                        await websocket.close(code=1008, reason="Access denied")
                        return
                elif not share:
                    print(f"WebSocket auth failed: Device {device_id} not owned or shared with user {user_id}")
                    await websocket.close(code=1008, reason="Access denied")
                    return

            print(f"WebSocket authenticated successfully for user {user_id} connecting to device {device_id}")

            # Accept the WebSocket connection
            await websocket.accept()
            user_connections[device_id].append(websocket)

            # Request full sync from device when user connects
            if device_id in device_connections:
                try:
                    await device_connections[device_id].send_json({"type": "request_full_sync"})
                    print(f"Sent request_full_sync to device {device_id} for new user connection")
                except:
                    pass

            try:
                while True:
                    data = await websocket.receive_json()
                    print(f"Received from user for {device_id}: {json.dumps(data)}")
                    # Relay command to device
                    if device_id in device_connections:
                        await device_connections[device_id].send_json(data)
                        print(f"Relayed to device {device_id}: {json.dumps(data)}")
                    else:
                        await websocket.send_json({"error": "Device offline"})
                        print(f"Device {device_id} offline, could not relay")
            except WebSocketDisconnect:
                user_connections[device_id].remove(websocket)
                print(f"User disconnected from device {device_id}")

    except Exception as e:
        print(f"WebSocket authentication error for device {device_id}: {e}")
        import traceback
        traceback.print_exc()
        await websocket.close(code=1008, reason=str(e))
        return
