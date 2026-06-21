@echo off
setlocal enabledelayedexpansion

echo === Starting Crop ^& Compress Build Script ===
echo Detected Operating System: Windows

:: 1. Setup virtual environment for a clean build (reduces executable size)
if not exist ".venv\" (
    echo Creating virtual environment .venv...
    python -m venv .venv
)

echo Activating virtual environment...
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo ERROR: Could not find virtual environment activation script.
    exit /b 1
)

:: 2. Upgrade pip and install dependencies
echo Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

:: 3. Run PyInstaller
echo Building Windows Executable (.exe)...

set "ICON_ARG="
if exist "icon\app.ico" (
    set "ICON_ARG=--icon=icon\app.ico"
) else (
    for %%F in (icon\*.ico) do (
        set "ICON_ARG=--icon=%%F"
        goto :found_icon
    )
)
:found_icon

if defined ICON_ARG (
    echo Using Windows icon: !ICON_ARG!
)

pyinstaller --noconfirm --clean --onefile --windowed !ICON_ARG! --name="CropAndCompress" crop_and_compress.py

echo =========================================
echo SUCCESS: Windows Build complete!
echo Output is located at: dist\CropAndCompress.exe
echo =========================================

endlocal
