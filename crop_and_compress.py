#!/usr/bin/env python3
"""
Crop & Compress — quick macOS batch image tool.
Select files, draw a crop rectangle, pick a scale factor, and save.
Built with PyQt6 for a native macOS look.
"""

from app.logger import setup_logging
# Initialize logging and exception hooks before importing main
setup_logging()

from app.main_window import main

if __name__ == "__main__":
    main()
