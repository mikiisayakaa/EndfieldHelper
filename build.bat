@echo off
echo Endfield Helper - Building executable...
echo.

rem Change to the directory where this batch file is located
cd /d "%~dp0"

rem Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

echo [1/4] Checking Python...
python --version

echo.
echo [2/4] Installing/updating PyInstaller...
pip install pyinstaller -q

echo.
echo [3/4] Cleaning old dist files...
if exist dist rmdir /s /q dist

echo.
echo [4/4] Building executable...
pyinstaller build_config.spec -y --distpath dist --workpath build

if errorlevel 1 (
    echo.
    echo ERROR: Packaging failed!
    pause
    exit /b 1
)

echo.
echo SUCCESS! Executable created at: dist\Endfield Helper\
echo.
echo Contents:
echo - Endfield Helper.exe (main application)
echo - configs\ (configuration files)
echo - templates\ (template images)
echo.
echo You can now distribute the "Endfield Helper" folder to users.
echo.
pause
