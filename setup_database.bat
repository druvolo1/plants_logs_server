@echo off
REM Database Setup Launcher
REM Launches the database setup GUI

echo ========================================
echo Plant Logs Server - Database Setup
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
) else if exist ".venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
) else (
    echo No virtual environment found, using system Python
)

echo.
echo Checking dependencies...

REM Check if dotenv is installed
python -c "import dotenv" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Required packages not found. Installing dependencies...
    echo This may take a minute...
    echo.
    python -m pip install -r requirements-setup.txt
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install dependencies
        echo Please run: pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo.
    echo Dependencies installed successfully!
)

echo.
echo Launching Database Setup GUI...
echo.

REM Run the setup script
python setup_db.py

REM Check if there was an error
if errorlevel 1 (
    echo.
    echo ERROR: Setup script failed
    pause
    exit /b 1
)

echo.
echo Setup GUI closed
pause
