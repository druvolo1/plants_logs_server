# app/routers/pages.py
"""
HTML page routes for the web application.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
import jwt

from app.models import User

router = APIRouter(tags=["pages"])

templates = Jinja2Templates(directory="templates")

# Temporary storage for pending device pairings (device_id -> device_info)
# This avoids sessionStorage issues when redirecting to login
pending_pairings = {}


def get_current_user_dependency():
    """Import and return current_user dependency"""
    from app.main import current_user
    return current_user


def get_secret():
    """Import and return SECRET"""
    from app.main import SECRET
    return SECRET


def get_async_session_maker():
    """Import and return async_session_maker"""
    from app.main import async_session_maker
    return async_session_maker


# Landing page - redirects based on authentication status and user type
@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    # Try to get current user
    cookie = request.cookies.get("auth_cookie")

    if not cookie:
        # Not logged in, go to login page
        return RedirectResponse("/login")

    # Try to decode token and get user
    try:
        async_session_maker = get_async_session_maker()
        SECRET = get_secret()

        async with async_session_maker() as session:
            payload = jwt.decode(
                cookie,
                SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False}
            )
            user_id = payload.get("sub")

            if user_id:
                user_id = int(user_id)
                result = await session.execute(select(User).where(User.id == user_id))
                user = result.scalars().first()

                if user:
                    # Check if user is suspended (handle None as False)
                    is_suspended = getattr(user, 'is_suspended', None)
                    is_active = user.is_active

                    print(f"Root route check for {user.email}: is_suspended={is_suspended}, is_active={is_active}")

                    # Normalize is_suspended to boolean (handle None, 0, 1, True, False)
                    if is_suspended is None or is_suspended is False or is_suspended == 0:
                        is_suspended = False
                    else:
                        is_suspended = True

                    if is_suspended:
                        print(f"Root route: {user.email} is SUSPENDED - showing suspended page")
                        response = templates.TemplateResponse("suspended.html", {"request": request}, status_code=403)
                        response.delete_cookie("auth_cookie")
                        return response

                    # Check if user is pending approval
                    if not is_active:
                        print(f"Root route: {user.email} is PENDING - showing pending approval page")
                        response = templates.TemplateResponse("pending_approval.html", {"request": request}, status_code=403)
                        response.delete_cookie("auth_cookie")
                        return response

                    # User is active and not suspended - redirect to dashboard
                    if user.is_superuser:
                        return RedirectResponse("/dashboard")
                    else:
                        return RedirectResponse("/dashboard")
    except:
        pass

    # If anything fails, go to login
    return RedirectResponse("/login")


# Login page
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


# Registration page
@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


# Device pairing initiation (no auth required - stores params server-side)
# This now uses the standalone pairing page with built-in login
@router.get("/pair-device", response_class=HTMLResponse)
async def device_pair_initiation(request: Request):
    """Device pairing initiation - shows standalone pairing page with login"""
    # Get device info from query params
    device_id = request.query_params.get('device_id')
    device_name = request.query_params.get('name', 'Environment Sensor')
    mac_address = request.query_params.get('mac')
    model = request.query_params.get('model', 'HNENVCO2')
    manufacturer = request.query_params.get('manufacturer', 'HerbNerdz')
    sw_version = request.query_params.get('sw_version', '2.0')
    hw_version = request.query_params.get('hw_version', '1')

    if not device_id or not mac_address:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Invalid pairing request - missing device information"
        })

    # Store device info server-side with timestamp for cleanup
    pending_pairings[device_id] = {
        "device_id": device_id,
        "device_name": device_name,
        "mac_address": mac_address,
        "model": model,
        "manufacturer": manufacturer,
        "sw_version": sw_version,
        "hw_version": hw_version,
        "timestamp": datetime.utcnow()
    }

    # Check if user is already authenticated
    is_authenticated = False
    try:
        auth_cookie = request.cookies.get("auth_cookie")
        if auth_cookie:
            try:
                current_user = get_current_user_dependency()
                user = await current_user(request)
                is_authenticated = True
            except:
                pass
    except:
        pass

    # Show standalone pairing page (handles both login and pairing)
    # Filter out timestamp (not JSON serializable) before passing to template
    device_info_for_template = {k: v for k, v in pending_pairings[device_id].items() if k != 'timestamp'}

    return templates.TemplateResponse("device_pair_standalone.html", {
        "request": request,
        "device_info": device_info_for_template,
        "is_authenticated": is_authenticated
    })


# Device pairing page (requires authentication) - legacy route
@router.get("/pair-device-auth", response_class=HTMLResponse)
async def device_pair_page(request: Request, user: User = Depends(get_current_user_dependency())):
    """Device pairing page for environment sensors - requires authentication"""
    device_id = request.query_params.get('device_id')

    # Get device info from server storage
    if not device_id or device_id not in pending_pairings:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Device pairing session expired or not found. Please start the pairing process again from your sensor."
        })

    device_info = pending_pairings[device_id]

    # Create a copy of device_info without the timestamp (not JSON serializable)
    device_info_for_template = {k: v for k, v in device_info.items() if k != 'timestamp'}

    return templates.TemplateResponse("device_pair.html", {
        "request": request,
        "user": user,
        "device_info": device_info_for_template
    })


# Standalone pairing page (after OAuth redirect)
@router.get("/pair-device-standalone", response_class=HTMLResponse)
async def device_pair_standalone(request: Request):
    """Standalone pairing page - used after OAuth login redirect"""
    device_id = request.query_params.get('device_id')

    # Get device info from server storage
    if not device_id or device_id not in pending_pairings:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": "Device pairing session expired or not found. Please start the pairing process again from your sensor."
        })

    # Check if user is authenticated (should be after OAuth)
    is_authenticated = False
    try:
        auth_cookie = request.cookies.get("auth_cookie")
        if auth_cookie:
            try:
                current_user = get_current_user_dependency()
                user = await current_user(request)
                is_authenticated = True
            except:
                pass
    except:
        pass

    device_info = pending_pairings[device_id]
    device_info_for_template = {k: v for k, v in device_info.items() if k != 'timestamp'}

    return templates.TemplateResponse("device_pair_standalone.html", {
        "request": request,
        "device_info": device_info_for_template,
        "is_authenticated": is_authenticated
    })


# Dashboard
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: User = Depends(get_current_user_dependency())):
    # Check for impersonation mode (admin viewing as another user)
    impersonating_user = None
    display_user = user  # The user whose data to display

    if user.is_superuser:
        impersonated_id = request.cookies.get("impersonate_user_id")
        if impersonated_id:
            try:
                from app.main import get_db
                from sqlalchemy.ext.asyncio import AsyncSession

                # Get impersonated user from database
                async for session in get_db():
                    target = await session.get(User, int(impersonated_id))
                    if target:
                        impersonating_user = target  # The user being impersonated
                        display_user = target  # Show their data
                    break
            except Exception as e:
                print(f"Error loading impersonated user: {e}")

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": display_user,
        "actual_user": user,  # The real admin user
        "impersonating_user": impersonating_user  # Set if in impersonation mode
    })


# Helper to get impersonation context for pages
async def get_impersonation_context(request: Request, user: User) -> dict:
    """Get impersonation context for page templates."""
    context = {
        "user": user,
        "actual_user": user,
        "impersonating_user": None
    }

    if user.is_superuser:
        impersonated_id = request.cookies.get("impersonate_user_id")
        if impersonated_id:
            try:
                from app.main import get_db

                async for session in get_db():
                    target = await session.get(User, int(impersonated_id))
                    if target:
                        context["impersonating_user"] = target
                        context["user"] = target  # Display as impersonated user
                    break
            except Exception as e:
                print(f"Error loading impersonated user: {e}")

    return context


# Devices page
@router.get("/devices", response_class=HTMLResponse)
async def devices_page(request: Request, user: User = Depends(get_current_user_dependency())):
    context = await get_impersonation_context(request, user)
    return templates.TemplateResponse("devices.html", {"request": request, **context})


# Plants page
@router.get("/plants", response_class=HTMLResponse)
async def plants_page(request: Request, user: User = Depends(get_current_user_dependency())):
    context = await get_impersonation_context(request, user)
    return templates.TemplateResponse("plants.html", {"request": request, **context})


# Locations page
@router.get("/locations", response_class=HTMLResponse)
async def locations_page(request: Request, user: User = Depends(get_current_user_dependency())):
    context = await get_impersonation_context(request, user)
    return templates.TemplateResponse("locations.html", {"request": request, **context})


# Templates page
@router.get("/templates", response_class=HTMLResponse)
async def templates_page_route(request: Request, user: User = Depends(get_current_user_dependency())):
    context = await get_impersonation_context(request, user)
    return templates.TemplateResponse("templates.html", {"request": request, **context})
