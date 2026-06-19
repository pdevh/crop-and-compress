#!/usr/bin/env python3
"""
Crop & Compress — quick macOS batch image tool.
Select files, draw a crop rectangle, pick a scale factor, and save.
Built with PyQt6 for a native macOS look.
"""

import sys
import os
from pathlib import Path
from enum import Enum, auto

from PyQt6.QtCore import Qt, QRect, QPoint, QSize
from PyQt6.QtGui import (
    QPixmap, QPainter, QPen, QColor, QImage, QAction, QIcon,
    QDragEnterEvent, QDropEvent, QFont, QKeySequence
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSpinBox, QCheckBox, QFileDialog,
    QMessageBox, QSizePolicy, QScrollArea, QGroupBox, QComboBox,
    QSlider, QToolBar, QStatusBar, QStyle
)
from PIL import Image

# ─────────────────────────────────────────────────────────────────────────────
# Canvas widget: shows the image and lets the user draw/resize a crop rect
# ─────────────────────────────────────────────────────────────────────────────

class DragMode(Enum):
    NONE = auto()
    CREATE = auto()
    MOVE = auto()
    RESIZE_TL = auto() # Top-Left
    RESIZE_TR = auto() # Top-Right
    RESIZE_BL = auto() # Bottom-Left
    RESIZE_BR = auto() # Bottom-Right
    RESIZE_T = auto()  # Top
    RESIZE_B = auto()  # Bottom
    RESIZE_L = auto()  # Left
    RESIZE_R = auto()  # Right


class CropCanvas(QLabel):
    """Image preview + interactive resizable crop rectangle."""

    HANDLE_SIZE = 10

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(400, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background: #222; border-radius: 8px;")
        self.setText("📂  Select files or drag a folder to begin")
        
        f = self.font()
        f.setPointSize(14)
        self.setFont(f)

        self._pixmap: QPixmap | None = None
        self._scale = 1.0
        self._offset = QPoint(0, 0)

        # Crop state (original-image coords and canvas coords)
        self._crop_orig: tuple[int, int, int, int] | None = None
        self._crop_rect = QRect()
        self._has_crop = False
        self._excluded = False
        
        self._drag_mode = DragMode.NONE
        self._drag_start_pos = QPoint()
        self._drag_start_rect = QRect()
        
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    # ── public API ───────────────────────────────────────────────────────

    def set_image(self, pixmap: QPixmap, crop_orig: tuple[int, int, int, int] | None = None, excluded: bool = False):
        self._pixmap = pixmap
        self._crop_orig = crop_orig
        self._excluded = excluded
        
        if excluded:
            self.setCursor(Qt.CursorShape.ForbiddenCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
            
        self._update_layout()
        self.update()

    def set_excluded(self, excluded: bool):
        self._excluded = excluded
        if excluded:
            self.setCursor(Qt.CursorShape.ForbiddenCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def clear_crop(self):
        self._has_crop = False
        self._crop_rect = QRect()
        self._crop_orig = None
        self.update()
        if hasattr(self, 'crop_changed_callback') and self.crop_changed_callback:
            self.crop_changed_callback()

    @property
    def has_crop(self):
        return self._has_crop

    def crop_rect_original(self) -> tuple[int, int, int, int] | None:
        """Return crop rectangle in original-image coordinates, or None."""
        if not self._has_crop and self._drag_mode != DragMode.CREATE:
            if self._drag_mode == DragMode.NONE:
                return None
        if self._pixmap is None or not self._crop_rect.isValid():
            return None
        
        # Ensure correct orientation (top-left to bottom-right)
        r = self._crop_rect.normalized()
        
        # canvas → original image
        ox, oy = self._offset.x(), self._offset.y()
        s = self._scale
        x0 = max(0, (r.left() - ox) / s)
        y0 = max(0, (r.top() - oy) / s)
        x1 = min(self._pixmap.width(), (r.right() - ox) / s)
        y1 = min(self._pixmap.height(), (r.bottom() - oy) / s)
        
        if x1 <= x0 or y1 <= y0:
            return None
        return (int(x0), int(y0), int(x1), int(y1))

    # ── internal layout ──────────────────────────────────────────────────

    def _update_layout(self):
        if self._pixmap is None:
            return
        cw, ch = self.width(), self.height()
        pw, ph = self._pixmap.width(), self._pixmap.height()
        self._scale = min(cw / pw, ch / ph, 1.0)
        sw = int(pw * self._scale)
        sh = int(ph * self._scale)
        self._offset = QPoint((cw - sw) // 2, (ch - sh) // 2)
        
        # Re-sync screen coordinates from stored original crop coordinates
        if self._crop_orig:
            ox, oy = self._offset.x(), self._offset.y()
            s = self._scale
            x0 = int(self._crop_orig[0] * s + ox)
            y0 = int(self._crop_orig[1] * s + oy)
            x1 = int(self._crop_orig[2] * s + ox)
            y1 = int(self._crop_orig[3] * s + oy)
            self._crop_rect = QRect(QPoint(x0, y0), QPoint(x1, y1))
            self._has_crop = True
        else:
            self._crop_rect = QRect()
            self._has_crop = False

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_layout()

    # ── painting ─────────────────────────────────────────────────────────

    def paintEvent(self, e):
        if self._pixmap is None:
            super().paintEvent(e)
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # dark bg for the widget area
        p.fillRect(self.rect(), QColor("#222"))

        # draw scaled image
        sw = int(self._pixmap.width() * self._scale)
        sh = int(self._pixmap.height() * self._scale)
        target = QRect(self._offset.x(), self._offset.y(), sw, sh)
        p.drawPixmap(target, self._pixmap)

        if self._excluded:
            # Paint dark red overlay
            p.fillRect(target, QColor(20, 10, 10, 180))
            p.setPen(QColor("#ff5555"))
            f = self.font()
            f.setPointSize(24)
            f.setBold(True)
            p.setFont(f)
            p.drawText(target, Qt.AlignmentFlag.AlignCenter, "✗ EXCLUDED FROM EXPORT")
            p.end()
            return

        # draw crop rect
        if self._has_crop or self._drag_mode == DragMode.CREATE:
            r = self._crop_rect.normalized()

            # dim outside crop
            p.setBrush(QColor(0, 0, 0, 150))
            p.setPen(Qt.PenStyle.NoPen)
            # top
            p.drawRect(QRect(0, 0, self.width(), r.top()))
            # bottom
            p.drawRect(QRect(0, r.bottom() + 1, self.width(), self.height() - r.bottom() - 1))
            # left
            p.drawRect(QRect(0, r.top(), r.left(), r.height() + 1))
            # right
            p.drawRect(QRect(r.right() + 1, r.top(), self.width() - r.right() - 1, r.height() + 1))

            # dashed green border
            pen = QPen(QColor("#00ff88"), 2, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
            
            # draw handles if we have a valid crop
            if self._has_crop:
                p.setPen(QPen(QColor("#000000"), 1))
                p.setBrush(QColor("#ffffff"))
                hs = self.HANDLE_SIZE
                hhs = hs // 2
                
                # Corners
                p.drawRect(r.left() - hhs, r.top() - hhs, hs, hs)     # TL
                p.drawRect(r.right() - hhs, r.top() - hhs, hs, hs)    # TR
                p.drawRect(r.left() - hhs, r.bottom() - hhs, hs, hs)  # BL
                p.drawRect(r.right() - hhs, r.bottom() - hhs, hs, hs) # BR
                
                # Edges
                mid_x = r.left() + r.width() // 2
                mid_y = r.top() + r.height() // 2
                p.drawRect(mid_x - hhs, r.top() - hhs, hs, hs)        # T
                p.drawRect(mid_x - hhs, r.bottom() - hhs, hs, hs)     # B
                p.drawRect(r.left() - hhs, mid_y - hhs, hs, hs)       # L
                p.drawRect(r.right() - hhs, mid_y - hhs, hs, hs)      # R

            # size label
            crop = self.crop_rect_original()
            if crop:
                cw = crop[2] - crop[0]
                ch = crop[3] - crop[1]
                label = f"{cw}×{ch}"
                p.setPen(QColor("#00ff88"))
                f = self.font()
                f.setPointSize(11)
                f.setBold(True)
                p.setFont(f)
                p.drawText(r.left() + 6, r.top() - 6, label)

        p.end()

    # ── mouse events ─────────────────────────────────────────────────────
    
    def _get_drag_mode(self, pos: QPoint) -> DragMode:
        if not self._has_crop:
            return DragMode.CREATE
            
        r = self._crop_rect.normalized()
        hs = self.HANDLE_SIZE
        
        def in_handle(x, y):
            return QRect(x - hs, y - hs, hs*2, hs*2).contains(pos)
            
        if in_handle(r.left(), r.top()): return DragMode.RESIZE_TL
        if in_handle(r.right(), r.top()): return DragMode.RESIZE_TR
        if in_handle(r.left(), r.bottom()): return DragMode.RESIZE_BL
        if in_handle(r.right(), r.bottom()): return DragMode.RESIZE_BR
        
        mid_x = r.left() + r.width() // 2
        mid_y = r.top() + r.height() // 2
        
        if in_handle(mid_x, r.top()): return DragMode.RESIZE_T
        if in_handle(mid_x, r.bottom()): return DragMode.RESIZE_B
        if in_handle(r.left(), mid_y): return DragMode.RESIZE_L
        if in_handle(r.right(), mid_y): return DragMode.RESIZE_R
        
        if r.contains(pos):
            return DragMode.MOVE
            
        return DragMode.CREATE

    def mousePressEvent(self, e):
        if self._excluded:
            return
        if e.button() == Qt.MouseButton.LeftButton and self._pixmap:
            self.setFocus()  # Grab focus to divert from SpinBoxes!
            self._drag_mode = self._get_drag_mode(e.pos())
            self._drag_start_pos = e.pos()
            
            if self._drag_mode == DragMode.CREATE:
                self._crop_rect = QRect(e.pos(), e.pos())
                self._has_crop = False
            else:
                self._drag_start_rect = self._crop_rect
                
            self.update()

    def mouseMoveEvent(self, e):
        if self._excluded:
            return
        if self._drag_mode != DragMode.NONE:
            delta = e.pos() - self._drag_start_pos
            r = QRect(self._drag_start_rect)
            
            # Constrain movement/resizing to image bounds
            sw = int(self._pixmap.width() * self._scale)
            sh = int(self._pixmap.height() * self._scale)
            img_rect = QRect(self._offset.x(), self._offset.y(), sw, sh)
            
            def constrain_x(x): return max(img_rect.left(), min(x, img_rect.right()))
            def constrain_y(y): return max(img_rect.top(), min(y, img_rect.bottom()))
            
            if self._drag_mode == DragMode.CREATE:
                self._crop_rect = QRect(
                    QPoint(constrain_x(self._drag_start_pos.x()), constrain_y(self._drag_start_pos.y())),
                    QPoint(constrain_x(e.pos().x()), constrain_y(e.pos().y()))
                )
            elif self._drag_mode == DragMode.MOVE:
                r.translate(delta)
                if r.left() < img_rect.left(): r.moveLeft(img_rect.left())
                if r.right() > img_rect.right(): r.moveRight(img_rect.right())
                if r.top() < img_rect.top(): r.moveTop(img_rect.top())
                if r.bottom() > img_rect.bottom(): r.moveBottom(img_rect.bottom())
                self._crop_rect = r
            else:
                # Resizing
                x = constrain_x(e.pos().x())
                y = constrain_y(e.pos().y())
                
                if self._drag_mode in (DragMode.RESIZE_TL, DragMode.RESIZE_L, DragMode.RESIZE_BL):
                    r.setLeft(x)
                if self._drag_mode in (DragMode.RESIZE_TR, DragMode.RESIZE_R, DragMode.RESIZE_BR):
                    r.setRight(x)
                if self._drag_mode in (DragMode.RESIZE_TL, DragMode.RESIZE_T, DragMode.RESIZE_TR):
                    r.setTop(y)
                if self._drag_mode in (DragMode.RESIZE_BL, DragMode.RESIZE_B, DragMode.RESIZE_BR):
                    r.setBottom(y)
                    
                self._crop_rect = r
                
            self.update()

    def mouseReleaseEvent(self, e):
        if self._excluded:
            return
        if self._drag_mode != DragMode.NONE:
            self._crop_rect = self._crop_rect.normalized()
            if self._crop_rect.width() > 5 and self._crop_rect.height() > 5:
                self._has_crop = True
                self._crop_orig = self.crop_rect_original()
            else:
                self._has_crop = False
                self._crop_rect = QRect()
                self._crop_orig = None
                
            self._drag_mode = DragMode.NONE
            self.update()
            
            if hasattr(self, 'crop_changed_callback') and self.crop_changed_callback:
                self.crop_changed_callback()


# ─────────────────────────────────────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Crop & Compress")
        self.setMinimumSize(900, 650)
        self.resize(1100, 800)
        self.setAcceptDrops(True)

        self.files: list[Path] = []
        self.current_idx = 0
        self.output_dir: Path | None = None
        self.crops: list[tuple[int, int, int, int] | None] = []
        self.included: list[bool] = []
        self.exported: set[int] = set()

        self._build_ui()
        self._create_menu_bar()
        
        # Disable buttons initially and setup status
        self._update_export_buttons()
        self._update_status_bar()
        
        # Globally intercept keys when active/focused
        QApplication.instance().installEventFilter(self)

    def closeEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        super().closeEvent(event)

    def _create_menu_bar(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        open_action = QAction("Open Files…", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._pick_files)
        file_menu.addAction(open_action)
        
        out_action = QAction("Set Output Folder…", self)
        out_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        out_action.triggered.connect(self._pick_output)
        file_menu.addAction(out_action)
        
        file_menu.addSeparator()
        
        export_curr_action = QAction("Export Current Image", self)
        export_curr_action.setShortcut(QKeySequence("Ctrl+E"))
        export_curr_action.triggered.connect(self._apply_current)
        file_menu.addAction(export_curr_action)
        
        export_all_action = QAction("Export All Included", self)
        export_all_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
        export_all_action.triggered.connect(self._apply_all)
        self.menu_export_all = export_all_action
        file_menu.addAction(export_all_action)
        
        file_menu.addSeparator()
        
        close_action = QAction("Close Window", self)
        close_action.setShortcut(QKeySequence("Ctrl+W"))
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)
        
        # Edit menu
        edit_menu = menubar.addMenu("Edit")
        
        select_all_action = QAction("Select All", self)
        select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        select_all_action.triggered.connect(self._select_all_noop)
        edit_menu.addAction(select_all_action)
        
        edit_menu.addSeparator()
        
        reset_action = QAction("Reset Crop", self)
        reset_action.setShortcut(QKeySequence("Ctrl+R"))
        reset_action.triggered.connect(self.canvas.clear_crop)
        edit_menu.addAction(reset_action)
        
        edit_menu.addSeparator()
        
        include_all_action = QAction("Include All Images", self)
        include_all_action.triggered.connect(self._include_all)
        edit_menu.addAction(include_all_action)
        
        exclude_all_action = QAction("Exclude All Images", self)
        exclude_all_action.triggered.connect(self._exclude_all)
        edit_menu.addAction(exclude_all_action)
        
        # Navigate menu
        nav_menu = menubar.addMenu("Navigate")
        
        prev_action = QAction("Previous Image", self)
        prev_action.setShortcut(QKeySequence(Qt.Key.Key_Left))
        prev_action.triggered.connect(self._prev)
        nav_menu.addAction(prev_action)
        
        next_action = QAction("Next Image", self)
        next_action.setShortcut(QKeySequence(Qt.Key.Key_Right))
        next_action.triggered.connect(self._next)
        nav_menu.addAction(next_action)

    def _select_all_noop(self):
        pass

    # ── Global Key Interceptor ───────────────────────────────────────────

    def eventFilter(self, watched, event):
        if event.type() == event.Type.KeyPress:
            # If a modal dialog is open (like file picker or message box), let it handle the keys
            if QApplication.activeModalWidget() is not None:
                return super().eventFilter(watched, event)
                
            key = event.key()
            if key == Qt.Key.Key_Left:
                self._prev()
                return True
            elif key == Qt.Key.Key_Right:
                self._next()
                return True
            elif key == Qt.Key.Key_Space:
                self._toggle_included()
                return True
            elif key == Qt.Key.Key_Escape:
                self.canvas.clear_crop()
                return True
                
        return super().eventFilter(watched, event)

    # ── UI build ─────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ── Top bar: file selection ──────────────────────────────────────
        top = QHBoxLayout()
        btn_files = QPushButton("📂 Select Files…")
        btn_files.clicked.connect(self._pick_files)
        top.addWidget(btn_files)

        self.file_label = QLabel("No files selected  (or drag & drop)")
        
        palette = self.file_label.palette()
        color = palette.color(self.file_label.foregroundRole())
        color.setAlpha(180)
        palette.setColor(self.file_label.foregroundRole(), color)
        self.file_label.setPalette(palette)
        
        top.addWidget(self.file_label, 1)
        main_layout.addLayout(top)

        # ── Settings row ─────────────────────────────────────────────────
        settings_row = QHBoxLayout()

        # Scale group
        sg = QGroupBox("Scale")
        sgl = QHBoxLayout(sg)
        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(5, 100)
        self.scale_spin.setValue(100)
        self.scale_spin.setSuffix(" %")
        self.scale_spin.setSingleStep(5)
        sgl.addWidget(self.scale_spin)
        settings_row.addWidget(sg)

        # Max dimension group
        mg = QGroupBox("Max long edge")
        mgl = QHBoxLayout(mg)
        self.maxdim_spin = QSpinBox()
        self.maxdim_spin.setRange(0, 8192)
        self.maxdim_spin.setValue(2048)
        self.maxdim_spin.setSuffix(" px")
        self.maxdim_spin.setSingleStep(256)
        self.maxdim_spin.setSpecialValueText("No limit")
        mgl.addWidget(self.maxdim_spin)
        settings_row.addWidget(mg)

        # Output Format group
        fg = QGroupBox("Format")
        fgl = QHBoxLayout(fg)
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Original", "JPEG", "PNG", "WebP"])
        fgl.addWidget(self.format_combo)
        settings_row.addWidget(fg)

        # Quality group
        qg = QGroupBox("Quality (JPEG/WebP)")
        qgl = QHBoxLayout(qg)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(10, 100)
        self.quality_spin.setValue(85)
        self.quality_spin.setSingleStep(5)
        qgl.addWidget(self.quality_spin)
        settings_row.addWidget(qg)

        # Output group
        og = QGroupBox("Output Destination")
        ogl = QHBoxLayout(og)
        self.replace_check = QCheckBox("Replace originals")
        self.replace_check.toggled.connect(self._toggle_output)
        ogl.addWidget(self.replace_check)
        btn_out = QPushButton("📁 Folder…")
        btn_out.clicked.connect(self._pick_output)
        ogl.addWidget(btn_out)
        self.out_label = QLabel("(not set)")
        self.out_label.setPalette(palette)
        ogl.addWidget(self.out_label, 1)
        settings_row.addWidget(og, 1)

        main_layout.addLayout(settings_row)

        # ── Canvas ───────────────────────────────────────────────────────
        self.canvas = CropCanvas()
        self.canvas.setCursor(Qt.CursorShape.CrossCursor)
        self.canvas.crop_changed_callback = self._on_crop_changed
        main_layout.addWidget(self.canvas, 1)

        # ── Bottom bar: nav + actions ────────────────────────────────────
        bot = QHBoxLayout()

        self.prev_btn = QPushButton("◀ Prev")
        self.prev_btn.clicked.connect(self._prev)
        bot.addWidget(self.prev_btn)

        self.nav_label = QLabel("")
        self.nav_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        f = self.nav_label.font()
        f.setBold(True)
        self.nav_label.setFont(f)
        
        bot.addWidget(self.nav_label, 1)

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self._next)
        bot.addWidget(self.next_btn)

        bot.addSpacing(30)

        btn_reset = QPushButton("↺ Reset Crop")
        btn_reset.clicked.connect(self.canvas.clear_crop)
        bot.addWidget(btn_reset)

        self.btn_apply1 = QPushButton("✂ Export Current (⌘E)")
        self.btn_apply1.clicked.connect(self._apply_current)
        bot.addWidget(self.btn_apply1)

        self.btn_apply = QPushButton("✂ Export All Included (0) (⌘Shift+E)")
        self.btn_apply.clicked.connect(self._apply_all)
        f = self.btn_apply.font()
        f.setBold(True)
        self.btn_apply.setFont(f)
        bot.addWidget(self.btn_apply)

        main_layout.addLayout(bot)

        # ── Status bar ───────────────────────────────────────────────────
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        
        self.status_stats_label = QLabel("")
        self.status.addPermanentWidget(self.status_stats_label)
        
        self.status.showMessage("Ready — select or drag images to get started")

        # Clear focus from spinboxes when Enter/Return is pressed
        self.scale_spin.lineEdit().returnPressed.connect(self.scale_spin.clearFocus)
        self.maxdim_spin.lineEdit().returnPressed.connect(self.maxdim_spin.clearFocus)
        self.quality_spin.lineEdit().returnPressed.connect(self.quality_spin.clearFocus)

    # ── Drag & drop ──────────────────────────────────────────────────────

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        urls = e.mimeData().urls()
        exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}
        found_paths = []
        for u in urls:
            p = Path(u.toLocalFile())
            if p.is_dir():
                # Scan direct children of directory (non-recursive)
                for child in p.iterdir():
                    if child.is_file() and child.suffix.lower() in exts:
                        found_paths.append(child)
            elif p.is_file() and p.suffix.lower() in exts:
                found_paths.append(p)
                
        if found_paths:
            found_paths.sort(key=lambda x: x.name.lower())
            self.files = found_paths
            self.current_idx = 0
            self.crops = [None] * len(self.files)
            self.included = [True] * len(self.files)
            self.exported = set()
            self.file_label.setText(f"{len(self.files)} file(s) loaded")
            self._load_current()

    # ── File picking ─────────────────────────────────────────────────────

    def _pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select images", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tiff *.tif)"
        )
        if not paths:
            return
        found_paths = [Path(p) for p in paths]
        found_paths.sort(key=lambda x: x.name.lower())
        self.files = found_paths
        self.current_idx = 0
        self.crops = [None] * len(self.files)
        self.included = [True] * len(self.files)
        self.exported = set()
        self.file_label.setText(f"{len(self.files)} file(s) loaded")
        self._load_current()

    def _pick_output(self):
        d = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if d:
            self.output_dir = Path(d)
            self.out_label.setText(self.output_dir.name)
            self.replace_check.setChecked(False)

    def _toggle_output(self, checked):
        if checked:
            self.out_label.setText("(replacing originals)")
        elif self.output_dir:
            self.out_label.setText(self.output_dir.name)
        else:
            self.out_label.setText("(not set)")

    # ── Navigation ───────────────────────────────────────────────────────

    def _load_current(self):
        if not self.files:
            return
        path = self.files[self.current_idx]
        pm = QPixmap(str(path))
        if pm.isNull():
            QMessageBox.warning(self, "Error", f"Cannot open:\n{path.name}")
            return
            
        crop = self.crops[self.current_idx]
        excluded = not self.included[self.current_idx]
        self.canvas.set_image(pm, crop, excluded)
        
        self._update_nav()
        self._update_status_bar()
        self._update_export_buttons()
        
        self.status.showMessage(
            f"{path.name}  —  {pm.width()}×{pm.height()}  —  "
            f"{path.stat().st_size // 1024} KB"
        )

    def _update_nav(self):
        if not self.files:
            self.nav_label.setText("No images loaded")
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            return
            
        n = len(self.files)
        idx = self.current_idx
        path = self.files[idx]
        
        inc_str = "<span style='color: #00cc66;'>✓ Included</span>" if self.included[idx] else "<span style='color: #ff4444;'>✗ Excluded</span>"
        exp_str = " · <span style='color: #33aaff;'>✓ Exported</span>" if idx in self.exported else ""
        
        self.nav_label.setText(f"{idx + 1} / {n}  ·  <b>{path.name}</b>  ·  {inc_str}{exp_str}")
        self.prev_btn.setEnabled(idx > 0)
        self.next_btn.setEnabled(idx < n - 1)

    def _prev(self):
        if not self.files:
            return
        # Save current crop before moving
        self.crops[self.current_idx] = self.canvas.crop_rect_original()
        if self.current_idx > 0:
            self.current_idx -= 1
            self._load_current()

    def _next(self):
        if not self.files:
            return
        # Save current crop before moving
        self.crops[self.current_idx] = self.canvas.crop_rect_original()
        if self.current_idx < len(self.files) - 1:
            self.current_idx += 1
            self._load_current()

    def _toggle_included(self):
        if not self.files:
            return
        idx = self.current_idx
        self.included[idx] = not self.included[idx]
        self.canvas.set_excluded(not self.included[idx])
        self._update_nav()
        self._update_status_bar()
        self._update_export_buttons()

    def _include_all(self):
        if not self.files:
            return
        self.included = [True] * len(self.files)
        self.canvas.set_excluded(False)
        self._update_nav()
        self._update_status_bar()
        self._update_export_buttons()

    def _exclude_all(self):
        if not self.files:
            return
        self.included = [False] * len(self.files)
        self.canvas.set_excluded(True)
        self._update_nav()
        self._update_status_bar()
        self._update_export_buttons()

    def _on_crop_changed(self):
        if not self.files:
            return
        self.crops[self.current_idx] = self.canvas.crop_rect_original()
        self._update_status_bar()

    def _update_status_bar(self):
        if not self.files:
            self.status_stats_label.setText("")
            return
            
        n = len(self.files)
        inc_count = sum(1 for i in self.included if i)
        exp_count = len(self.exported)
        
        crop = self.canvas.crop_rect_original()
        if crop:
            w = crop[2] - crop[0]
            h = crop[3] - crop[1]
            crop_str = f"Crop: {w}×{h}"
        else:
            crop_str = "Crop: Full image"
            
        stats = f"{inc_count} of {n} included  ·  {exp_count} exported  ·  {crop_str}"
        self.status_stats_label.setText(stats)

    def _update_export_buttons(self):
        if not self.files:
            self.btn_apply1.setEnabled(False)
            self.btn_apply.setEnabled(False)
            self.btn_apply.setText("✂ Export All Included (0) (⌘Shift+E)")
            if hasattr(self, 'menu_export_all'):
                self.menu_export_all.setText("Export All Included")
            return
            
        self.btn_apply1.setEnabled(True)
        inc_count = sum(1 for i in self.included if i)
        self.btn_apply.setEnabled(inc_count > 0)
        self.btn_apply.setText(f"✂ Export All Included ({inc_count}) (⌘⇧E)")
        if hasattr(self, 'menu_export_all'):
            self.menu_export_all.setText(f"Export All Included ({inc_count})")

    # ── Processing ───────────────────────────────────────────────────────

    def _ensure_output(self) -> bool:
        """Make sure we have a valid output destination. Returns False if cancelled."""
        if self.replace_check.isChecked():
            return True
        if self.output_dir and self.output_dir.is_dir():
            return True
        d = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if not d:
            return False
        self.output_dir = Path(d)
        self.out_label.setText(self.output_dir.name)
        return True

    def _process_image(self, path: Path, crop: tuple[int, int, int, int] | None = None) -> Path:
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
        scale = self.scale_spin.value() / 100.0
        if scale < 1.0:
            nw = max(1, int(img.size[0] * scale))
            nh = max(1, int(img.size[1] * scale))
            img = img.resize((nw, nh), Image.LANCZOS)

        # max long-edge
        maxdim = self.maxdim_spin.value()
        if maxdim > 0:
            w, h = img.size
            if max(w, h) > maxdim:
                ratio = maxdim / max(w, h)
                img = img.resize(
                    (max(1, int(w * ratio)), max(1, int(h * ratio))),
                    Image.LANCZOS
                )

        # Determine output extension
        format_str = self.format_combo.currentText()
        ext = path.suffix.lower()
        if format_str == "PNG":
            ext = ".png"
        elif format_str == "JPEG":
            ext = ".jpg"
        elif format_str == "WebP":
            ext = ".webp"
        
        # Determine output path
        if self.replace_check.isChecked():
            out_path = path.with_suffix(ext)
        else:
            out_path = self.output_dir / path.with_suffix(ext).name
            
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
            img.save(out_path, "JPEG", quality=self.quality_spin.value(), optimize=True)
        elif ext == ".webp":
            img.save(out_path, "WebP", quality=self.quality_spin.value(), method=4)
        else:
            img.save(out_path)

        return out_path

    def _apply_current(self):
        if not self.files:
            return
        if not self._ensure_output():
            return
            
        # Capture current crop
        crop = self.canvas.crop_rect_original()
        self.crops[self.current_idx] = crop
        path = self.files[self.current_idx]
        
        try:
            saved = self._process_image(path, crop)
            sz = saved.stat().st_size / 1024
            self.exported.add(self.current_idx)
            self._update_nav()
            self._update_status_bar()
            self.status.showMessage(f"✓ Saved {saved.name}  ({sz:.0f} KB)")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _apply_all(self):
        if not self.files:
            return
            
        inc_count = sum(1 for i in self.included if i)
        if inc_count == 0:
            QMessageBox.information(self, "Export", "No images are included for export.")
            return
            
        if not self._ensure_output():
            return
            
        if self.replace_check.isChecked():
            reply = QMessageBox.warning(
                self, "Confirm Replace",
                f"Are you sure you want to replace {inc_count} original file(s)? This cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Save current crop
        self.crops[self.current_idx] = self.canvas.crop_rect_original()

        ok, fail = 0, 0
        total_sz = 0
        for idx, path in enumerate(self.files):
            if not self.included[idx]:
                continue
            try:
                crop = self.crops[idx]
                saved = self._process_image(path, crop)
                total_sz += saved.stat().st_size
                self.exported.add(idx)
                ok += 1
            except Exception as e:
                print(f"FAIL {path}: {e}", file=sys.stderr)
                fail += 1
                
        self._update_nav()
        self._update_status_bar()
        
        msg = f"Processed {ok} file(s)."
        if fail:
            msg += f"  ({fail} failed)"
            
        if ok > 0:
            avg_sz = (total_sz / ok) / 1024
            self.status.showMessage(f"✓ Exported {ok} images (avg {avg_sz:.0f} KB)")
        else:
            self.status.showMessage(f"✓ Export complete: {msg}")
            
        QMessageBox.information(self, "Batch complete", msg)


# ─────────────────────────────────────────────────────────────────────────────
# Entry
# ─────────────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Crop & Compress")

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
