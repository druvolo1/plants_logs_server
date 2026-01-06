# app/routers/auth.py
"""
Authentication endpoints including OAuth, login, registration, and user preferences.
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import User
from app.schemas import UserCreate
from app.utils.login_tracker import record_login

router = APIRouter(tags=["auth"])
api_router = APIRouter(prefix="/api/user", tags=["user-api"])

templates = Jinja2Templates(directory="templates")


def get_current_user_dependency():
    """Import and return current_user dependency"""
    from app.main import current_user
    return current_user


def get_db_dependency():
    """Import and return get_db dependency"""
    from app.main import get_db
    return get_db


def get_user_manager_dependency():
    """Import and return get_user_manager dependency"""
    from app.main import get_user_manager
    return get_user_manager


def get_jwt_strategy_dependency():
    """Import and return get_jwt_strategy dependency"""
    from app.main import get_jwt_strategy
    return get_jwt_strategy


def get_google_oauth_client():
    """Import and return google_oauth_client"""
    from app.main import google_oauth_client
    return google_oauth_client


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request, prioritizing public IPs."""
    import ipaddress

    def is_private_ip(ip_str: str) -> bool:
        """Check if an IP address is private/local."""
        try:
            ip = ipaddress.ip_address(ip_str)
            return ip.is_private or ip.is_loopback or ip.is_link_local
        except ValueError:
            return True  # Invalid IP, treat as private

    # Check for X-Forwarded-For header (proxy/load balancer)
    # Format: "client, proxy1, proxy2" - we want the first public IP
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Split by comma and check each IP
        ips = [ip.strip() for ip in forwarded_for.split(",")]
        for ip in ips:
            if ip and not is_private_ip(ip):
                return ip
        # If all IPs are private, return the first one
        if ips:
            return ips[0]

    # Check for X-Real-IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip and not is_private_ip(real_ip):
        return real_ip

    # Fall back to direct client IP
    if request.client:
        return request.client.host

    return None


def get_user_agent(request: Request) -> str:
    """Extract user agent from request."""
    return request.headers.get("User-Agent", None)


# Google OAuth authorize
@router.get("/auth/google/authorize", response_model=dict)
async def google_authorize_custom(request: Request):
    google_oauth_client = get_google_oauth_client()
    redirect_uri = request.url_for("auth:google.callback")
    auth_url = await google_oauth_client.get_authorization_url(
        str(redirect_uri),
        state=None,
        scope=["openid", "email", "profile"]
    )
    return {"authorization_url": auth_url}


# Google OAuth callback
@router.get("/auth/google/callback", name="auth:google.callback")
async def google_callback_custom(
    request: Request,
    code: str,
    state: str = None,
    manager = Depends(get_user_manager_dependency()),
    strategy = Depends(get_jwt_strategy_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    google_oauth_client = get_google_oauth_client()
    try:
        # Get OAuth token
        token = await google_oauth_client.get_access_token(code, request.url_for("auth:google.callback"))

        # Get user info
        user_info = await google_oauth_client.get_id_email(token["access_token"])
        account_id = user_info[0]
        account_email = user_info[1]

        # Call our oauth_callback to create/get user
        user = await manager.oauth_callback(
            oauth_name="google",
            access_token=token["access_token"],
            account_id=account_id,
            account_email=account_email,
            expires_at=token.get("expires_at"),
            refresh_token=token.get("refresh_token"),
            associate_by_email=True,
            is_verified_by_default=False,
        )

        print(f"OAuth callback returned user: {user.email}, is_active={user.is_active}, is_suspended={getattr(user, 'is_suspended', None)}")

        # Check if user is suspended
        is_suspended = getattr(user, 'is_suspended', None)
        if is_suspended is None or is_suspended is False or is_suspended == 0:
            is_suspended = False
        else:
            is_suspended = True

        if is_suspended:
            return templates.TemplateResponse("suspended.html", {"request": request})

        # Check if user is pending approval
        if not user.is_active:
            return templates.TemplateResponse("pending_approval.html", {"request": request})

        # User is active - log them in
        token_str = await strategy.write_token(user)

        # Record login activity
        await record_login(
            session=session,
            user=user,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request)
        )

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Login Successful</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                .spinner {{ border: 4px solid #f3f3f3; border-top: 4px solid #3498db;
                           border-radius: 50%; width: 40px; height: 40px;
                           animation: spin 1s linear infinite; margin: 20px auto; }}
                @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
            </style>
        </head>
        <body>
            <h1>Login Successful!</h1>
            <div class="spinner"></div>
            <p>Redirecting...</p>
            <script>
                setTimeout(function() {{
                    window.location.href = '/dashboard';
                }}, 500);
            </script>
        </body>
        </html>
        """

        response = HTMLResponse(content=html_content, status_code=200)
        response.set_cookie(
            key="auth_cookie",
            value=token_str,
            httponly=True,
            max_age=3600,
            samesite="lax"
        )
        return response

    except Exception as e:
        print(f"ERROR in OAuth callback endpoint: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return templates.TemplateResponse("login.html", {"request": request, "error": "oauth_failed"})


# Registration form handler
@router.post("/auth/register")
async def register_user(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    manager = Depends(get_user_manager_dependency())
):
    from fastapi_users import exceptions
    try:
        user_create = UserCreate(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_active=False,  # Pending approval
            is_verified=False,
            is_suspended=False  # Explicitly set not suspended
        )
        await manager.create(user_create)
        return templates.TemplateResponse("registration_pending.html", {"request": request})
    except exceptions.UserAlreadyExists:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "A user with this email already exists"
        })
    except Exception as e:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Registration failed. Please try again."
        })


# JWT login form handler
@router.post("/auth/jwt/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(None),
    device_id: str = Form(None),
    manager = Depends(get_user_manager_dependency()),
    strategy = Depends(get_jwt_strategy_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    from fastapi.security import OAuth2PasswordRequestForm

    # Create credentials object
    credentials = OAuth2PasswordRequestForm(username=username, password=password, scope="")

    try:
        user = await manager.authenticate(credentials)

        if user is None:
            return RedirectResponse("/login?error=invalid_credentials", status_code=303)

        # Create token
        token = await strategy.write_token(user)

        # Record login activity
        await record_login(
            session=session,
            user=user,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request)
        )

        # Redirect based on next parameter if present, otherwise dashboard
        redirect_url = "/dashboard"
        if next and device_id:
            redirect_url = f"{next}?device_id={device_id}"
        elif next:
            redirect_url = next

        response = RedirectResponse(redirect_url, status_code=303)
        response.set_cookie(
            key="auth_cookie",
            value=token,
            httponly=True,
            max_age=3600,
            samesite="lax"
        )
        return response

    except HTTPException as e:
        if e.detail == "PENDING_APPROVAL":
            return templates.TemplateResponse("pending_approval.html", {"request": request})
        elif e.detail == "SUSPENDED":
            return templates.TemplateResponse("suspended.html", {"request": request})
        return RedirectResponse("/login?error=invalid_credentials", status_code=303)
    except Exception as e:
        print(f"Login error: {e}")
        return RedirectResponse("/login?error=server_error", status_code=303)


# Logout
@router.get("/auth/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("auth_cookie")
    return response


# JSON login for AJAX requests (used by device pairing modal)
@router.post("/auth/api/login")
async def api_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    manager = Depends(get_user_manager_dependency()),
    strategy = Depends(get_jwt_strategy_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    from fastapi.responses import JSONResponse
    from fastapi.security import OAuth2PasswordRequestForm

    print(f"[API Login] Received login request for: {username}")

    # Create credentials object
    credentials = OAuth2PasswordRequestForm(username=username, password=password, scope="")

    try:
        user = await manager.authenticate(credentials)

        if user is None:
            return JSONResponse({"success": False, "detail": "Invalid email or password"}, status_code=401)

        # Create token
        token = await strategy.write_token(user)

        # Record login activity
        await record_login(
            session=session,
            user=user,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request)
        )

        # Return JSON response with cookie
        # Note: samesite="none" and secure=True required for cross-origin iframe usage
        response = JSONResponse({"success": True, "message": "Login successful"})
        response.set_cookie(
            key="auth_cookie",
            value=token,
            httponly=True,
            max_age=3600,
            samesite="none",
            secure=True  # Required when samesite=none
        )
        return response

    except HTTPException as e:
        if e.detail == "PENDING_APPROVAL":
            return JSONResponse({"success": False, "detail": "Account pending approval"}, status_code=403)
        elif e.detail == "SUSPENDED":
            return JSONResponse({"success": False, "detail": "Account suspended"}, status_code=403)
        return JSONResponse({"success": False, "detail": "Invalid email or password"}, status_code=401)
    except Exception as e:
        print(f"API Login error: {e}")
        return JSONResponse({"success": False, "detail": "Server error"}, status_code=500)


# Get current user info API
@api_router.get("/me")
async def get_current_user_info(
    request: Request,
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    # Check for impersonation - return impersonated user's info if active
    effective_user = user
    is_impersonating = False

    if user.is_superuser:
        impersonated_id = request.cookies.get("impersonate_user_id")
        if impersonated_id:
            try:
                target = await session.get(User, int(impersonated_id))
                if target:
                    effective_user = target
                    is_impersonating = True
            except (ValueError, TypeError):
                pass

    return {
        "email": effective_user.email,
        "first_name": effective_user.first_name,
        "last_name": effective_user.last_name,
        "is_superuser": effective_user.is_superuser,
        "is_active": effective_user.is_active,
        "is_impersonating": is_impersonating,
        "actual_user_email": user.email if is_impersonating else None
    }


# Get dashboard preferences
@api_router.get("/dashboard-preferences")
async def get_dashboard_preferences(
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    # Refresh user from database to get latest preferences
    result = await session.execute(select(User).where(User.id == user.id))
    db_user = result.scalars().first()

    if db_user and db_user.dashboard_preferences:
        try:
            import json
            return json.loads(db_user.dashboard_preferences)
        except:
            return {}
    return {}


# Save dashboard preferences
@api_router.post("/dashboard-preferences")
async def save_dashboard_preferences(
    preferences: Dict[str, Any],
    user: User = Depends(get_current_user_dependency()),
    session: AsyncSession = Depends(get_db_dependency())
):
    import json

    # Get user from database
    result = await session.execute(select(User).where(User.id == user.id))
    db_user = result.scalars().first()

    if not db_user:
        raise HTTPException(404, "User not found")

    # Save preferences as JSON string
    db_user.dashboard_preferences = json.dumps(preferences)
    await session.commit()

    return {"status": "success", "message": "Preferences saved"}
