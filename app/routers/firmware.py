# app/routers/firmware.py
"""
Firmware management endpoints for OTA updates.
"""
import os
import hashlib
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models import User, Device, Firmware, DeviceFirmwareAssignment
from app.schemas import (
    FirmwareRead,
    FirmwareListItem,
    DeviceFirmwareAssignmentRead,
    FirmwareUpdateInfo,
)
from app.routers.websocket import device_connections

router = APIRouter(tags=["firmware"])

# Firmware storage directory (relative to app root)
FIRMWARE_STORAGE_DIR = "firmware_storage"


def get_current_admin_dependency():
    """Import and return current_admin dependency"""
    from app.main import current_admin
    return current_admin


def get_current_user_dependency():
    """Import and return current_user dependency"""
    from app.main import current_user
    return current_user


def get_db_dependency():
    """Import and return get_db dependency"""
    from app.main import get_db
    return get_db


def get_templates():
    """Import and return templates"""
    from app.main import templates
    return templates


def ensure_firmware_dir():
    """Ensure the firmware storage directory exists"""
    if not os.path.exists(FIRMWARE_STORAGE_DIR):
        os.makedirs(FIRMWARE_STORAGE_DIR)


async def _send_firmware_update_via_websocket(device_id: str):
    """Send firmware_update command to a device via WebSocket"""
    if device_id in device_connections:
        try:
            await device_connections[device_id].send_json({"type": "firmware_update"})
            print(f"[FIRMWARE] Sent firmware_update command via WebSocket to {device_id}")
        except Exception as e:
            print(f"[FIRMWARE] Failed to send firmware_update via WebSocket to {device_id}: {e}")
    else:
        print(f"[FIRMWARE] Device {device_id} not connected via WebSocket, cannot send firmware_update command")


def calculate_checksum(file_path: str) -> str:
    """Calculate SHA256 checksum of a file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


# HTML Pages

@router.get("/admin/firmware", response_class=HTMLResponse)
async def firmware_management_page(
    request: Request,
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Firmware management page (admin only)"""
    from sqlalchemy import func

    # Count pending users for sidebar badge
    pending_result = await session.execute(
        select(func.count(User.id)).where(User.is_active == False)
    )
    pending_count = pending_result.scalar() or 0

    return get_templates().TemplateResponse("admin_firmware.html", {
        "request": request,
        "user": admin,
        "active_page": "firmware",
        "pending_users_count": pending_count
    })


# API Endpoints - Admin Only

@router.get("/admin/firmware/list", response_model=List[FirmwareListItem])
async def list_all_firmware(
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency()),
    device_type: Optional[str] = None
):
    """List all firmware versions, optionally filtered by device type"""
    query = select(Firmware).order_by(Firmware.device_type, Firmware.created_at.desc())

    if device_type:
        query = query.where(Firmware.device_type == device_type)

    result = await session.execute(query)
    firmware_list = result.scalars().all()

    return firmware_list


# Device Firmware Assignments
# NOTE: These routes MUST come before /admin/firmware/{firmware_id} to avoid path conflicts

@router.get("/admin/firmware/assignments", response_model=List[DeviceFirmwareAssignmentRead])
async def list_firmware_assignments(
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """List all device-specific firmware assignments"""
    result = await session.execute(
        select(DeviceFirmwareAssignment, Device, Firmware)
        .join(Device, DeviceFirmwareAssignment.device_id == Device.id)
        .join(Firmware, DeviceFirmwareAssignment.firmware_id == Firmware.id)
    )

    assignments = []
    for assignment, device, firmware in result.all():
        assignments.append(DeviceFirmwareAssignmentRead(
            id=assignment.id,
            device_id=assignment.device_id,
            firmware_id=assignment.firmware_id,
            force_update=assignment.force_update,
            notes=assignment.notes,
            created_at=assignment.created_at,
            updated_at=assignment.updated_at,
            firmware_version=firmware.version,
            firmware_device_type=firmware.device_type,
            device_identifier=device.device_id,
            device_name=device.name
        ))

    return assignments


@router.post("/admin/firmware/assignments")
async def create_firmware_assignment(
    device_identifier: str = Form(...),  # device_id string
    firmware_id: int = Form(...),
    force_update: bool = Form(False),
    notes: str = Form(None),
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Assign a specific firmware version to a device.

    This overrides the "latest" firmware for this device, useful for:
    - Testing beta firmware on specific devices
    - Rolling back a device to an older version
    - Holding a device at a specific version
    """
    # Get device
    device_result = await session.execute(
        select(Device).where(Device.device_id == device_identifier)
    )
    device = device_result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    # Get firmware
    firmware_result = await session.execute(
        select(Firmware).where(Firmware.id == firmware_id)
    )
    firmware = firmware_result.scalars().first()

    if not firmware:
        raise HTTPException(404, "Firmware not found")

    # Verify device type matches
    if device.device_type != firmware.device_type:
        raise HTTPException(400, f"Firmware is for {firmware.device_type}, but device is {device.device_type}")

    # Check for existing assignment
    existing = await session.execute(
        select(DeviceFirmwareAssignment).where(
            DeviceFirmwareAssignment.device_id == device.id
        )
    )
    existing_assignment = existing.scalars().first()

    if existing_assignment:
        # Update existing assignment
        existing_assignment.firmware_id = firmware_id
        existing_assignment.force_update = force_update
        existing_assignment.notes = notes
        existing_assignment.assigned_by_user_id = admin.id
        existing_assignment.updated_at = datetime.utcnow()
        await session.commit()

        print(f"[FIRMWARE] Admin {admin.email} updated assignment for device {device_identifier}: "
              f"v{firmware.version} (force: {force_update})")

        # Send WebSocket command for valve_controller devices when force_update is enabled
        if force_update and device.device_type == 'valve_controller':
            await _send_firmware_update_via_websocket(device_identifier)

        return {
            "status": "success",
            "message": f"Updated firmware assignment to v{firmware.version}",
            "assignment_id": existing_assignment.id
        }
    else:
        # Create new assignment
        assignment = DeviceFirmwareAssignment(
            device_id=device.id,
            firmware_id=firmware_id,
            force_update=force_update,
            notes=notes,
            assigned_by_user_id=admin.id
        )
        session.add(assignment)
        await session.commit()
        await session.refresh(assignment)

        print(f"[FIRMWARE] Admin {admin.email} created assignment for device {device_identifier}: "
              f"v{firmware.version} (force: {force_update})")

        # Send WebSocket command for valve_controller devices when force_update is enabled
        if force_update and device.device_type == 'valve_controller':
            await _send_firmware_update_via_websocket(device_identifier)

        return {
            "status": "success",
            "message": f"Assigned firmware v{firmware.version} to device",
            "assignment_id": assignment.id
        }


@router.put("/admin/firmware/assignments/{assignment_id}/force-update")
async def set_force_update(
    assignment_id: int,
    force: bool = True,
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Set or clear the force_update flag on a device assignment"""
    result = await session.execute(
        select(DeviceFirmwareAssignment, Device)
        .join(Device, DeviceFirmwareAssignment.device_id == Device.id)
        .where(DeviceFirmwareAssignment.id == assignment_id)
    )
    row = result.first()

    if not row:
        raise HTTPException(404, "Assignment not found")

    assignment, device = row
    assignment.force_update = force
    assignment.updated_at = datetime.utcnow()
    await session.commit()

    # Send WebSocket command for valve_controller devices when force_update is enabled
    if force and device.device_type == 'valve_controller':
        await _send_firmware_update_via_websocket(device.device_id)

    return {
        "status": "success",
        "message": f"Force update {'enabled' if force else 'disabled'}"
    }


@router.delete("/admin/firmware/assignments/{assignment_id}")
async def delete_firmware_assignment(
    assignment_id: int,
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Remove a device-specific firmware assignment.
    The device will revert to using the "latest" firmware for its type.
    """
    result = await session.execute(
        select(DeviceFirmwareAssignment).where(DeviceFirmwareAssignment.id == assignment_id)
    )
    assignment = result.scalars().first()

    if not assignment:
        raise HTTPException(404, "Assignment not found")

    await session.delete(assignment)
    await session.commit()

    return {"status": "success", "message": "Assignment removed, device will use latest firmware"}


# Individual firmware routes (must come AFTER /assignments routes)

@router.get("/admin/firmware/{firmware_id}", response_model=FirmwareRead)
async def get_firmware_details(
    firmware_id: int,
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Get detailed firmware information including release notes"""
    result = await session.execute(
        select(Firmware).where(Firmware.id == firmware_id)
    )
    firmware = result.scalars().first()

    if not firmware:
        raise HTTPException(404, "Firmware not found")

    return firmware


@router.post("/admin/firmware/upload")
async def upload_firmware(
    device_type: str = Form(...),
    version: str = Form(...),
    release_notes: str = Form(None),
    is_prerelease: bool = Form(False),
    set_as_latest: bool = Form(False),
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Upload a new firmware binary.

    Args:
        device_type: Type of device (e.g., 'environmental', 'valve_controller')
        version: Semantic version string (e.g., '2.1.0', '2.2.0-beta.1')
        release_notes: Markdown release notes
        is_prerelease: Whether this is a beta/pre-release version
        set_as_latest: Whether to mark this as the latest stable version
        file: The firmware binary file (.bin)
    """
    ensure_firmware_dir()

    # Validate file extension
    if not file.filename.endswith('.bin'):
        raise HTTPException(400, "Firmware file must be a .bin file")

    # Check for duplicate version
    existing = await session.execute(
        select(Firmware).where(
            Firmware.device_type == device_type,
            Firmware.version == version
        )
    )
    if existing.scalars().first():
        raise HTTPException(400, f"Firmware version {version} already exists for {device_type}")

    # Create subdirectory for device type
    device_dir = os.path.join(FIRMWARE_STORAGE_DIR, device_type)
    if not os.path.exists(device_dir):
        os.makedirs(device_dir)

    # Save file with version in filename
    filename = f"{device_type}_{version}.bin"
    file_path = os.path.join(device_dir, filename)
    relative_path = os.path.join(device_type, filename)

    # Write file to disk
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Calculate checksum and file size
    file_size = len(content)
    checksum = calculate_checksum(file_path)

    # If setting as latest, unset current latest for this device type
    if set_as_latest:
        await session.execute(
            update(Firmware)
            .where(Firmware.device_type == device_type, Firmware.is_latest == True)
            .values(is_latest=False)
        )

    # Create firmware record
    firmware = Firmware(
        device_type=device_type,
        version=version,
        release_notes=release_notes,
        file_path=relative_path,
        file_size=file_size,
        checksum=checksum,
        is_latest=set_as_latest,
        is_prerelease=is_prerelease,
        uploaded_by_user_id=admin.id
    )

    session.add(firmware)
    await session.commit()
    await session.refresh(firmware)

    print(f"[FIRMWARE] Admin {admin.email} uploaded firmware: {device_type} v{version} "
          f"(size: {file_size} bytes, latest: {set_as_latest})")

    return {
        "status": "success",
        "firmware_id": firmware.id,
        "device_type": device_type,
        "version": version,
        "file_size": file_size,
        "checksum": checksum,
        "is_latest": set_as_latest
    }


@router.put("/admin/firmware/{firmware_id}/set-latest")
async def set_firmware_as_latest(
    firmware_id: int,
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Mark a firmware version as the latest stable release for its device type"""
    result = await session.execute(
        select(Firmware).where(Firmware.id == firmware_id)
    )
    firmware = result.scalars().first()

    if not firmware:
        raise HTTPException(404, "Firmware not found")

    # Unset current latest for this device type
    await session.execute(
        update(Firmware)
        .where(Firmware.device_type == firmware.device_type, Firmware.is_latest == True)
        .values(is_latest=False)
    )

    # Set this one as latest
    firmware.is_latest = True
    await session.commit()

    print(f"[FIRMWARE] Admin {admin.email} set {firmware.device_type} v{firmware.version} as latest")

    return {
        "status": "success",
        "message": f"{firmware.device_type} v{firmware.version} is now the latest stable version"
    }


@router.put("/admin/firmware/{firmware_id}/release-notes")
async def update_release_notes(
    firmware_id: int,
    release_notes: str = Form(...),
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Update the release notes for a firmware version"""
    result = await session.execute(
        select(Firmware).where(Firmware.id == firmware_id)
    )
    firmware = result.scalars().first()

    if not firmware:
        raise HTTPException(404, "Firmware not found")

    firmware.release_notes = release_notes
    await session.commit()

    return {"status": "success", "message": "Release notes updated"}


@router.delete("/admin/firmware/{firmware_id}")
async def delete_firmware(
    firmware_id: int,
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """Delete a firmware version (removes file and database record)"""
    result = await session.execute(
        select(Firmware).where(Firmware.id == firmware_id)
    )
    firmware = result.scalars().first()

    if not firmware:
        raise HTTPException(404, "Firmware not found")

    # Check if any devices are assigned to this firmware
    assignments = await session.execute(
        select(DeviceFirmwareAssignment).where(
            DeviceFirmwareAssignment.firmware_id == firmware_id
        )
    )
    if assignments.scalars().first():
        raise HTTPException(400, "Cannot delete firmware that is assigned to devices")

    # Delete the file
    file_path = os.path.join(FIRMWARE_STORAGE_DIR, firmware.file_path)
    if os.path.exists(file_path):
        os.remove(file_path)

    # Delete the record
    await session.delete(firmware)
    await session.commit()

    print(f"[FIRMWARE] Admin {admin.email} deleted firmware: {firmware.device_type} v{firmware.version}")

    return {"status": "success", "message": "Firmware deleted"}


# Force update from heartbeat settings modal

@router.put("/admin/devices/{device_id}/force-firmware-update")
async def force_device_firmware_update(
    device_id: str,
    admin: User = Depends(get_current_admin_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Force a device to update on its next heartbeat.

    If the device has a specific firmware assignment, it will update to that version.
    Otherwise, it will update to the latest firmware for its device type.
    """
    # Get device
    device_result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = device_result.scalars().first()

    if not device:
        raise HTTPException(404, "Device not found")

    # Check for existing assignment
    assignment_result = await session.execute(
        select(DeviceFirmwareAssignment).where(
            DeviceFirmwareAssignment.device_id == device.id
        )
    )
    assignment = assignment_result.scalars().first()

    if assignment:
        # Set force_update on existing assignment
        assignment.force_update = True
        assignment.updated_at = datetime.utcnow()
        await session.commit()

        # Get firmware version for message
        firmware_result = await session.execute(
            select(Firmware).where(Firmware.id == assignment.firmware_id)
        )
        firmware = firmware_result.scalars().first()
        version = firmware.version if firmware else "assigned version"

        print(f"[FIRMWARE] Admin {admin.email} forced update for {device_id} to v{version}")

        return {
            "status": "success",
            "message": f"Device will update to v{version} on next heartbeat"
        }
    else:
        # Create a new assignment with the latest firmware and force_update=True
        latest_result = await session.execute(
            select(Firmware).where(
                Firmware.device_type == device.device_type,
                Firmware.is_latest == True
            )
        )
        latest_firmware = latest_result.scalars().first()

        if not latest_firmware:
            raise HTTPException(404, f"No latest firmware found for device type {device.device_type}")

        assignment = DeviceFirmwareAssignment(
            device_id=device.id,
            firmware_id=latest_firmware.id,
            force_update=True,
            notes="Force update triggered by admin",
            assigned_by_user_id=admin.id
        )
        session.add(assignment)
        await session.commit()

        print(f"[FIRMWARE] Admin {admin.email} forced update for {device_id} to latest v{latest_firmware.version}")

        return {
            "status": "success",
            "message": f"Device will update to v{latest_firmware.version} on next heartbeat"
        }


# Public endpoint for firmware download (called by devices)

@router.get("/api/firmware/download/{device_type}/{version}")
async def download_firmware(
    device_type: str,
    version: str,
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Download a firmware binary.

    This endpoint is called by devices during OTA updates.
    No authentication required - the device already has the URL from the heartbeat.
    """
    result = await session.execute(
        select(Firmware).where(
            Firmware.device_type == device_type,
            Firmware.version == version
        )
    )
    firmware = result.scalars().first()

    if not firmware:
        raise HTTPException(404, "Firmware not found")

    file_path = os.path.join(FIRMWARE_STORAGE_DIR, firmware.file_path)

    if not os.path.exists(file_path):
        raise HTTPException(404, "Firmware file not found on server")

    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        filename=f"{device_type}_{version}.bin",
        headers={
            "X-Firmware-Version": version,
            "X-Firmware-Checksum": firmware.checksum or "",
            "X-Firmware-Size": str(firmware.file_size or 0)
        }
    )


# Endpoint for devices to check for updates (can also be integrated into heartbeat)

@router.get("/api/firmware/check/{device_id}")
async def check_firmware_update(
    device_id: str,
    current_version: str,
    session: AsyncSession = Depends(get_db_dependency())
) -> FirmwareUpdateInfo:
    """
    Check if a firmware update is available for a device.

    This can be called separately or the logic can be integrated into the heartbeat response.
    """
    # Get device
    device_result = await session.execute(
        select(Device).where(Device.device_id == device_id)
    )
    device = device_result.scalars().first()

    if not device:
        return FirmwareUpdateInfo(
            update_available=False,
            current_version=current_version
        )

    # Check for device-specific assignment
    assignment_result = await session.execute(
        select(DeviceFirmwareAssignment, Firmware)
        .join(Firmware, DeviceFirmwareAssignment.firmware_id == Firmware.id)
        .where(DeviceFirmwareAssignment.device_id == device.id)
    )
    assignment_row = assignment_result.first()

    if assignment_row:
        assignment, firmware = assignment_row

        # Device has a specific assignment
        if firmware.version != current_version:
            # Version mismatch - update available
            return FirmwareUpdateInfo(
                update_available=True,
                current_version=current_version,
                latest_version=firmware.version,
                firmware_url=f"/api/firmware/download/{firmware.device_type}/{firmware.version}",
                release_notes=firmware.release_notes,
                force_update=assignment.force_update,
                file_size=firmware.file_size,
                checksum=firmware.checksum
            )
        else:
            # Versions match - clear force_update flag if it was set (update completed)
            if assignment.force_update:
                assignment.force_update = False
                assignment.updated_at = datetime.utcnow()
                await session.commit()
                print(f"[FIRMWARE] Cleared force_update flag for device {device_id} - now at v{current_version}")

            return FirmwareUpdateInfo(
                update_available=False,
                current_version=current_version,
                latest_version=firmware.version
            )

    # No specific assignment - check for latest firmware
    latest_result = await session.execute(
        select(Firmware).where(
            Firmware.device_type == device.device_type,
            Firmware.is_latest == True
        )
    )
    latest_firmware = latest_result.scalars().first()

    if not latest_firmware:
        return FirmwareUpdateInfo(
            update_available=False,
            current_version=current_version
        )

    if latest_firmware.version != current_version:
        return FirmwareUpdateInfo(
            update_available=True,
            current_version=current_version,
            latest_version=latest_firmware.version,
            firmware_url=f"/api/firmware/download/{latest_firmware.device_type}/{latest_firmware.version}",
            release_notes=latest_firmware.release_notes,
            force_update=False,
            file_size=latest_firmware.file_size,
            checksum=latest_firmware.checksum
        )

    return FirmwareUpdateInfo(
        update_available=False,
        current_version=current_version,
        latest_version=latest_firmware.version
    )


# Release notes endpoint for users to preview

@router.get("/api/firmware/{device_type}/release-notes")
async def get_release_notes(
    device_type: str,
    version: Optional[str] = None,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    """
    Get release notes for a firmware version.

    If version is not specified, returns the latest firmware's release notes.
    """
    if version:
        result = await session.execute(
            select(Firmware).where(
                Firmware.device_type == device_type,
                Firmware.version == version
            )
        )
    else:
        result = await session.execute(
            select(Firmware).where(
                Firmware.device_type == device_type,
                Firmware.is_latest == True
            )
        )

    firmware = result.scalars().first()

    if not firmware:
        raise HTTPException(404, "Firmware not found")

    return {
        "device_type": device_type,
        "version": firmware.version,
        "release_notes": firmware.release_notes,
        "is_latest": firmware.is_latest,
        "is_prerelease": firmware.is_prerelease,
        "created_at": firmware.created_at
    }


@router.get("/api/firmware/{device_type}/changelog")
async def get_changelog(
    device_type: str,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency()),
    limit: int = 10
):
    """
    Get changelog (all versions with release notes) for a device type.
    """
    result = await session.execute(
        select(Firmware)
        .where(Firmware.device_type == device_type)
        .order_by(Firmware.created_at.desc())
        .limit(limit)
    )
    firmware_list = result.scalars().all()

    return {
        "device_type": device_type,
        "versions": [
            {
                "version": fw.version,
                "release_notes": fw.release_notes,
                "is_latest": fw.is_latest,
                "is_prerelease": fw.is_prerelease,
                "created_at": fw.created_at
            }
            for fw in firmware_list
        ]
    }
