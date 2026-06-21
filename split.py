import os

with open("crop_and_compress.py", "r") as f:
    lines = f.readlines()

def write_file(filename, start_line, end_line, extra_imports=""):
    with open(filename, "w") as f:
        f.write(extra_imports)
        f.writelines(lines[start_line-1:end_line])

os.makedirs("app", exist_ok=True)

# Write __init__.py
with open("app/__init__.py", "w") as f:
    f.write('"""App package."""\n')

imports = "".join(lines[11:37]) # from import sys ... load_dotenv()

# canvas.py: lines 38-376
canvas_imports = """from enum import Enum, auto
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor
from PyQt6.QtWidgets import QLabel, QSizePolicy
"""
write_file("app/canvas.py", 42, 376, canvas_imports)

# gemini_worker.py: lines 897-1029
worker_imports = """import os
import mimetypes
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal
from dotenv import load_dotenv

# Load .env relative to this file
load_dotenv(Path(__file__).resolve().parent.parent / '.env')
"""
write_file("app/gemini_worker.py", 901, 1029, worker_imports)

# widgets.py: lines 1031-1181
widgets_imports = """from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRect
from PyQt6.QtGui import QPixmap, QPainter, QColor
from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy
"""
write_file("app/widgets.py", 1035, 1181, widgets_imports)

# image_processing.py (extract logic from _process_image)
image_processing_code = """from pathlib import Path
from PIL import Image

def process_image(path: Path, crop: tuple[int, int, int, int] | None, 
                  scale_pct: int, max_dim: int, format_str: str, 
                  quality: int, output_dir: Path | None, replace_original: bool) -> Path:
    img = Image.open(path)
    img.load()
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    # crop
    if crop:
        w, h = img.size
        c = (max(0, crop[0]), max(0, crop[1]),
             min(w, crop[2]), min(h, crop[3]))
        img = img.crop(c)

    # scale %
    scale = scale_pct / 100.0
    if scale < 1.0:
        nw = max(1, int(img.size[0] * scale))
        nh = max(1, int(img.size[1] * scale))
        img = img.resize((nw, nh), Image.LANCZOS)

    # max long-edge
    if maxdim := max_dim:
        if maxdim > 0:
            w, h = img.size
            if max(w, h) > maxdim:
                ratio = maxdim / max(w, h)
                img = img.resize(
                    (max(1, int(w * ratio)), max(1, int(h * ratio))),
                    Image.LANCZOS
                )

    # Determine output extension
    ext = path.suffix.lower()
    if format_str == "PNG":
        ext = ".png"
    elif format_str == "JPEG":
        ext = ".jpg"
    elif format_str == "WebP":
        ext = ".webp"
    
    # Determine output path
    if replace_original:
        out_path = path.with_suffix(ext)
    else:
        out_path = output_dir / path.with_suffix(ext).name
        
        # Resolve name collisions
        base = out_path.stem
        suffix = out_path.suffix
        counter = 2
        while out_path.exists():
            out_path = out_path.with_name(f"{base}_{counter}{suffix}")
            counter += 1

    # Perform the actual save
    if ext == ".png":
        img.save(out_path, "PNG", optimize=True)
    elif ext in (".jpg", ".jpeg"):
        # If image has alpha and we are saving to JPEG, convert to RGB with white background
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
            img = bg
        img.save(out_path, "JPEG", quality=quality, optimize=True)
    elif ext == ".webp":
        img.save(out_path, "WebP", quality=quality, method=4)
    else:
        img.save(out_path)

    return out_path
"""
with open("app/image_processing.py", "w") as f:
    f.write(image_processing_code)

# crop_tab.py: lines 381-895 (minus process_image content which we extracted)
# Wait, I'll just write crop_tab directly via the script or modify it afterwards.
"""
We'll copy it directly, then use sed/replace to fix the process_image call.
"""
crop_tab_imports = """import sys
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox, 
    QCheckBox, QFileDialog, QMessageBox, QSizePolicy, QGroupBox, QComboBox
)
from .canvas import CropCanvas
from .image_processing import process_image
"""
write_file("app/crop_tab.py", 381, 895, crop_tab_imports)

# generate_tab.py: lines 1187-1752
generate_tab_imports = """import mimetypes
from datetime import datetime
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, 
    QMessageBox, QSizePolicy, QScrollArea, QGroupBox, QComboBox, QTextEdit, QFrame
)
from .gemini_worker import GeminiWorker, DEFAULT_SYSTEM_PROMPT
from .widgets import ReferenceThumbnail, SkeletonWidget
"""
write_file("app/generate_tab.py", 1187, 1752, generate_tab_imports)

# main_window.py: lines 1757-1981
main_window_imports = """import sys
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QDragEnterEvent, QDropEvent, QAction
from PyQt6.QtWidgets import QApplication, QMainWindow, QStatusBar, QLabel, QTabWidget
from .crop_tab import CropTab
from .generate_tab import GenerateTab
"""
write_file("app/main_window.py", 1757, 1976, main_window_imports)

print("Split complete.")
