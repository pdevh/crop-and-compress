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
    pyinstaller --noconfirm --clean --windowed \
        --name="CropAndCompress" \
        crop_and_compress.py
    
    echo "========================================="
    echo "SUCCESS: macOS Build complete!"
    echo "Output is located at: dist/CropAndCompress.app"
    echo "========================================="

elif [[ "${OS_NAME}" == "MINGW"* || "${OS_NAME}" == "MSYS"* || "${OS_NAME}" == "CYGWIN"* ]]; then
    echo "Building Windows Executable (.exe)..."
    pyinstaller --noconfirm --clean --onefile --windowed \
        --name="CropAndCompress" \
        crop_and_compress.py
        
    echo "========================================="
    echo "SUCCESS: Windows Build complete!"
    echo "Output is located at: dist/CropAndCompress.exe"
    echo "========================================="

else
    echo "Warning: Building on an untested OS: ${OS_NAME}."
    echo "Attempting generic single-file compilation..."
    pyinstaller --noconfirm --clean --onefile --windowed \
        --name="CropAndCompress" \
        crop_and_compress.py
fi
