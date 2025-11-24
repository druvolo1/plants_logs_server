"""Configuration and environment variables."""
from dotenv import load_dotenv
import os

load_dotenv()

# Database
DATABASE_URL = os.getenv("DATABASE_URL")
print("Loaded DATABASE_URL from .env:", DATABASE_URL)
DATABASE_URL = DATABASE_URL.replace("mariadb+mariadbconnector", "mariadb+aiomysql") if DATABASE_URL else None
print("Modified DATABASE_URL for async:", DATABASE_URL)

# Security
SECRET = os.getenv("SECRET_KEY") or "secret"
SERVER_URL = os.getenv("SERVER_URL")

# Google OAuth
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

# CORS Origins
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8000",
    SERVER_URL
] if SERVER_URL else ["http://localhost:3000", "http://localhost:8000"]
