@echo off
REM Sync Schema from Production Database
REM Extracts schema from production DB and displays it

echo ========================================
echo Sync Schema from Production Database
echo ========================================
echo.

REM Change to script directory
cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.9 or higher
    pause
    exit /b 1
)

REM Check if virtual environment exists and activate it
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo No virtual environment found, using system Python
)

echo.
echo Running schema sync script...
echo.

REM Run the sync script
python sync_schema_from_prod.py

REM Check if there was an error
if errorlevel 1 (
    echo.
    echo ERROR: Schema sync failed
    pause
    exit /b 1
)

echo.
echo ========================================
echo Schema sync complete!
echo ========================================
echo.
echo Please review the output above and update setup_db.py accordingly.
echo.
pause
