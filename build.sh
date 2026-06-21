#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "=== Starting Crop & Compress Build Script ==="

# 1. Determine OS
OS_NAME="$(uname -s)"
echo "Detected Operating System: ${OS_NAME}"

# 2. Setup virtual environment for a clean build (reduces executable size)
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment .venv..."
    python3 -m venv .venv
fi

echo "Activating virtual environment..."
# On Windows/Git Bash, the path is .venv/Scripts/activate, on macOS/Linux it is .venv/bin/activate
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
else
    echo "ERROR: Could not find virtual environment activation script."
    exit 1
fi

# 3. Upgrade pip and install dependencies
echo "Installing dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

# 4. Run PyInstaller based on OS
if [[ "${OS_NAME}" == "Darwin"* ]]; then
    echo "Building macOS App Bundle (.app)..."
    
    ICON_ARG=""
    if [ -f "icon/app.icns" ]; then
        ICON_ARG="--icon=icon/app.icns"
    else
        # Find any .icns file inside the icon/ directory
        FOUND_ICON=$(find icon -maxdepth 1 -name "*.icns" 2>/dev/null | head -n 1)
        if [ -n "$FOUND_ICON" ]; then
            ICON_ARG="--icon=$FOUND_ICON"
        fi
    fi
    
    if [ -n "$ICON_ARG" ]; then
        echo "Using macOS icon: $ICON_ARG"
    fi

    pyinstaller --noconfirm --clean --windowed \
        $ICON_ARG \
        --name="CropAndCompress" \
        crop_and_compress.py
    
    echo "========================================="
    echo "SUCCESS: macOS Build complete!"
    echo "Output is located at: dist/CropAndCompress.app"
    echo "========================================="

elif [[ "${OS_NAME}" == "MINGW"* || "${OS_NAME}" == "MSYS"* || "${OS_NAME}" == "CYGWIN"* ]]; then
    echo "Building Windows Executable (.exe)..."
    
    ICON_ARG=""
    if [ -f "icon/app.ico" ]; then
        ICON_ARG="--icon=icon/app.ico"
    else
        # Find any .ico file inside the icon/ directory
        FOUND_ICON=$(find icon -maxdepth 1 -name "*.ico" 2>/dev/null | head -n 1)
        if [ -n "$FOUND_ICON" ]; then
            ICON_ARG="--icon=$FOUND_ICON"
        fi
    fi
    
    if [ -n "$ICON_ARG" ]; then
        echo "Using Windows icon: $ICON_ARG"
    fi

    pyinstaller --noconfirm --clean --onefile --windowed \
        $ICON_ARG \
        --name="CropAndCompress" \
        crop_and_compress.py
        
    echo "========================================="
    echo "SUCCESS: Windows Build complete!"
    echo "Output is located at: dist/CropAndCompress.exe"
    echo "========================================="

else
    echo "Warning: Building on an untested OS: ${OS_NAME}."
    echo "Attempting generic single-file compilation..."
    
    ICON_ARG=""
    if [ -f "icon/app.ico" ]; then
        ICON_ARG="--icon=icon/app.ico"
    elif [ -f "icon/app.icns" ]; then
        ICON_ARG="--icon=icon/app.icns"
    else
        # Search for any .ico or .icns file
        FOUND_ICON=$(find icon -maxdepth 1 \( -name "*.ico" -o -name "*.icns" \) 2>/dev/null | head -n 1)
        if [ -n "$FOUND_ICON" ]; then
            ICON_ARG="--icon=$FOUND_ICON"
        fi
    fi
    
    pyinstaller --noconfirm --clean --onefile --windowed \
        $ICON_ARG \
        --name="CropAndCompress" \
        crop_and_compress.py
fi
