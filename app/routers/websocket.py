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

from app.models import User, Device, DeviceShare, LocationShare, DeviceFirmwareAssignment, DeviceConnection

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
    device = None  # Track device for cleanup
    device_added_to_connections = False  # Track if we added to device_connections

    try:
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

        # Mark device as online in database with explicit error handling
        try:
            await session.execute(update(Device).where(Device.device_id == device_id).values(is_online=True, last_seen=datetime.utcnow()))
            await session.commit()
            print(f"Set {device_id} online in DB")

            # Verify the update actually persisted
            verify_result = await session.execute(select(Device.is_online).where(Device.device_id == device_id))
            is_actually_online = verify_result.scalar()
            if not is_actually_online:
                print(f"CRITICAL ERROR: Database shows {device_id} still offline after update! Closing connection.")
                await websocket.close()
                return

        except Exception as db_error:
            print(f"CRITICAL ERROR: Failed to mark {device_id} online in DB: {db_error}")
            import traceback
            traceback.print_exc()
            await websocket.close()
            return

        device_connections[device_id] = websocket
        device_added_to_connections = True
        print(f"Added {device_id} to device_connections (total: {len(device_connections)} devices)")

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

        # Check if users are already viewing this device and notify device
        if len(user_connections[device_id]) > 0:
            try:
                await websocket.send_json({"type": "user_connected"})
                print(f"Sent user_connected to device {device_id} on connect (users already viewing)")
            except Exception as e:
                print(f"Failed to send user_connected to device {device_id}: {e}")

    except Exception as setup_error:
        print(f"CRITICAL ERROR during device setup for {device_id}: {setup_error}")
        import traceback
        traceback.print_exc()

        # Clean up if we partially set up
        if device_added_to_connections and device_id in device_connections:
            del device_connections[device_id]
            print(f"Removed {device_id} from device_connections after setup failure")

        # Try to mark offline in DB
        if device:
            try:
                await session.execute(update(Device).where(Device.device_id == device_id).values(is_online=False, last_seen=datetime.utcnow()))
                await session.commit()
                print(f"Marked {device_id} offline in DB after setup failure")
            except:
                pass

        try:
            await websocket.close()
        except:
            pass
        return

    try:
        while True:
            data = await websocket.receive_json()
            print(f"Received from device {device_id}: {json.dumps(data)}")

            # Handle device_info message for auto-detection
            if data.get('type') == 'device_info':
                device_type = data.get('device_type')
                device_name = data.get('device_name')
                capabilities = data.get('capabilities')
                firmware_version = data.get('firmware_version')
                mdns_hostname = data.get('mdns_hostname')
                ip_address = data.get('ip_address')

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

                # Store device name
                if device_name:
                    updates['name'] = device_name
                    print(f"Stored device name for {device_id}: {device_name}")

                # Store capabilities as JSON string
                if capabilities:
                    updates['capabilities'] = json.dumps(capabilities)
                    print(f"Stored capabilities for {device_id}: {capabilities}")

                # Store firmware version
                if firmware_version:
                    updates['firmware_version'] = firmware_version
                    print(f"Stored firmware version for {device_id}: {firmware_version}")

                # Store mDNS hostname
                if mdns_hostname:
                    updates['mdns_hostname'] = mdns_hostname
                    print(f"Stored mDNS hostname for {device_id}: {mdns_hostname}")

                # Store IP address
                if ip_address:
                    updates['ip_address'] = ip_address
                    print(f"Stored IP address for {device_id}: {ip_address}")

                # Update device in database
                if updates:
                    await session.execute(
                        update(Device)
                        .where(Device.device_id == device_id)
                        .values(**updates)
                    )
                    await session.commit()
                    print(f"Updated device {device_id} with: {updates}")

            # Handle device_connections message for auto-reporting connections
            if data.get('type') == 'device_connections':
                connections = data.get('connections', [])
                print(f"Device {device_id} reporting {len(connections)} connections")

                # Get the source device database record
                source_device_result = await session.execute(
                    select(Device).where(Device.device_id == device_id)
                )
                source_device = source_device_result.scalar_one_or_none()

                if not source_device:
                    print(f"ERROR: Source device {device_id} not found in database")
                else:
                    # Soft-delete all existing connections from this device
                    await session.execute(
                        update(DeviceConnection)
                        .where(
                            DeviceConnection.source_device_id == source_device.id,
                            DeviceConnection.removed_at == None
                        )
                        .values(removed_at=datetime.utcnow())
                    )
                    print(f"Soft-deleted existing connections for device {device_id}")

                    # Create new connections
                    for conn_data in connections:
                        target_device_id = conn_data.get('target_device_id')
                        connection_type = conn_data.get('connection_type')
                        config = conn_data.get('config')

                        if not target_device_id or not connection_type:
                            print(f"WARNING: Invalid connection data: {conn_data}")
                            continue

                        # Look up target device by device_id (UUID)
                        target_device_result = await session.execute(
                            select(Device).where(Device.device_id == target_device_id)
                        )
                        target_device = target_device_result.scalar_one_or_none()

                        if not target_device:
                            print(f"WARNING: Target device {target_device_id} not found")
                            continue

                        # Create the connection
                        new_connection = DeviceConnection(
                            source_device_id=source_device.id,
                            target_device_id=target_device.id,
                            connection_type=connection_type,
                            config=json.dumps(config) if config else None,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )
                        session.add(new_connection)
                        print(f"Created connection: {device_id} -> {target_device_id} ({connection_type})")

                    # Commit all changes
                    await session.commit()
                    print(f"Successfully updated {len(connections)} connections for device {device_id}")

            # Handle device name updates from device
            if data.get('type') == 'device_name_update':
                device_name = data.get('device_name')
                if device_name:
                    await session.execute(
                        update(Device)
                        .where(Device.device_id == device_id)
                        .values(name=device_name)
                    )
                    await session.commit()
                    device.name = device_name
                    print(f"Updated device name for {device_id}: {device_name}")

                    # Notify all connected users of the name change
                    for user_ws in user_connections[device_id]:
                        try:
                            await user_ws.send_json({
                                "type": "device_name_change",
                                "device_id": device_id,
                                "name": device_name
                            })
                        except:
                            pass

                    # Find all devices that have connections TO this device (as target)
                    # and notify users viewing those devices to refresh
                    connections_result = await session.execute(
                        select(DeviceConnection)
                        .where(
                            DeviceConnection.target_device_id == device.id,
                            DeviceConnection.removed_at == None
                        )
                    )
                    connected_from_devices = connections_result.scalars().all()

                    # Get the source device IDs
                    for conn in connected_from_devices:
                        source_device_result = await session.execute(
                            select(Device).where(Device.id == conn.source_device_id)
                        )
                        source_device = source_device_result.scalar_one_or_none()

                        if source_device:
                            # Notify users viewing the source device to refresh
                            for user_ws in user_connections.get(source_device.device_id, []):
                                try:
                                    await user_ws.send_json({
                                        "type": "connected_device_name_change",
                                        "source_device_id": source_device.device_id,
                                        "target_device_id": device_id,
                                        "target_device_name": device_name
                                    })
                                    print(f"Notified users of {source_device.device_id} about name change of connected device {device_id}")
                                except:
                                    pass

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
        import traceback
        traceback.print_exc()
    finally:
        # Always clean up and mark device offline, regardless of how connection ended
        print(f"Cleaning up device connection: {device_id}")

        # Remove from device_connections with verification
        if device_id in device_connections:
            del device_connections[device_id]
            print(f"Removed {device_id} from device_connections (remaining: {len(device_connections)} devices)")
        else:
            print(f"WARNING: {device_id} was not in device_connections during cleanup")

        # Mark device offline in database
        try:
            await session.execute(update(Device).where(Device.device_id == device_id).values(is_online=False, last_seen=datetime.utcnow()))
            await session.commit()
            print(f"Set {device_id} offline in DB")

            # Verify the offline status was set
            verify_result = await session.execute(select(Device.is_online).where(Device.device_id == device_id))
            is_still_online = verify_result.scalar()
            if is_still_online:
                print(f"WARNING: Database still shows {device_id} as online after cleanup!")

        except Exception as db_error:
            print(f"ERROR setting {device_id} offline in DB: {db_error}")
            import traceback
            traceback.print_exc()

        # Notify all connected users that the device went offline
        user_count = len(user_connections[device_id])
        if user_count > 0:
            print(f"Notifying {user_count} user(s) that {device_id} went offline")
            for user_ws in user_connections[device_id]:
                try:
                    await user_ws.send_json({"type": "device_status", "online": False})
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

            # Notify device if this is the first user connecting
            is_first_user = len(user_connections[device_id]) == 1

            # Request full sync from device when user connects
            if device_id in device_connections:
                try:
                    await device_connections[device_id].send_json({"type": "request_full_sync"})
                    print(f"Sent request_full_sync to device {device_id} for new user connection")

                    # Notify device that users are now viewing (only for first user)
                    if is_first_user:
                        await device_connections[device_id].send_json({"type": "user_connected"})
                        print(f"Sent user_connected to device {device_id} (first user connected)")
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

                # Notify device if this was the last user disconnecting
                is_last_user = len(user_connections[device_id]) == 0
                if is_last_user and device_id in device_connections:
                    try:
                        await device_connections[device_id].send_json({"type": "user_disconnected"})
                        print(f"Sent user_disconnected to device {device_id} (last user disconnected)")
                    except:
                        pass

    except Exception as e:
        print(f"WebSocket authentication error for device {device_id}: {e}")
        import traceback
        traceback.print_exc()
        await websocket.close(code=1008, reason=str(e))
        return
