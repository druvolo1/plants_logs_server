@echo off
REM Run migration 004 using Python

cd /d "%~dp0"

REM Check if virtual environment exists and activate it
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo No virtual environment found, using system Python
)

echo.
echo Running migration 004...
echo.

python run_migration_004.py

if errorlevel 1 (
    echo.
    echo ERROR: Migration failed
    pause
    exit /b 1
)

echo.
pause
