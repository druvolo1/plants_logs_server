"""Security utilities and JWT strategy."""
from fastapi_users.authentication import JWTStrategy
from .config import SECRET

def get_jwt_strategy() -> JWTStrategy:
    """Get JWT authentication strategy."""
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600 * 24 * 7)  # 7 days
