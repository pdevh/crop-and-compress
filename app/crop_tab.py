import sys
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox, 
    QCheckBox, QFileDialog, QMessageBox, QSizePolicy, QGroupBox, QComboBox
)
from .canvas import CropCanvas
from .image_processing import process_image
class CropTab(QWidget):
    """The original Crop & Compress UI, now housed in its own tab widget."""
    
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.setAcceptDrops(True)
        
        self.files: list[Path] = []
        self.current_idx = 0
        self.output_dir: Path | None = None
        self.crops: list[tuple[int, int, int, int] | None] = []
        self.included: list[bool] = []
        self.exported: set[int] = set()
        
        self._build_ui()
        self._update_export_buttons()

    # ── UI build ─────────────────────────────────────────────────────────

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
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
        
        palette2 = self.out_label.palette()
        color2 = palette2.color(self.out_label.foregroundRole())
        color2.setAlpha(180)
        palette2.setColor(self.out_label.foregroundRole(), color2)
        self.out_label.setPalette(palette2)
        
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
        
        self.parent_window.status.showMessage(
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
            self.parent_window.status_stats_label.setText("")
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
        self.parent_window.status_stats_label.setText(stats)

    def _update_export_buttons(self):
        if not self.files:
            self.btn_apply1.setEnabled(False)
            self.btn_apply.setEnabled(False)
            self.btn_apply.setText("✂ Export All Included (0) (⌘Shift+E)")
            if hasattr(self.parent_window, 'menu_export_all'):
                self.parent_window.menu_export_all.setText("Export All Included")
            return
            
        self.btn_apply1.setEnabled(True)
        inc_count = sum(1 for i in self.included if i)
        self.btn_apply.setEnabled(inc_count > 0)
        self.btn_apply.setText(f"✂ Export All Included ({inc_count}) (⌘⇧E)")
        if hasattr(self.parent_window, 'menu_export_all'):
            self.parent_window.menu_export_all.setText(f"Export All Included ({inc_count})")

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
            saved = process_image(
                path, crop,
                self.scale_spin.value(),
                self.maxdim_spin.value(),
                self.format_combo.currentText(),
                self.quality_spin.value(),
                self.output_dir,
                self.replace_check.isChecked()
            )
            sz = saved.stat().st_size / 1024
            self.exported.add(self.current_idx)
            self._update_nav()
            self._update_status_bar()
            self.parent_window.status.showMessage(f"✓ Saved {saved.name}  ({sz:.0f} KB)")
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
                saved = process_image(
                    path, crop,
                    self.scale_spin.value(),
                    self.maxdim_spin.value(),
                    self.format_combo.currentText(),
                    self.quality_spin.value(),
                    self.output_dir,
                    self.replace_check.isChecked()
                )
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
            self.parent_window.status.showMessage(f"✓ Exported {ok} images (avg {avg_sz:.0f} KB)")
        else:
            self.parent_window.status.showMessage(f"✓ Export complete: {msg}")
            
        QMessageBox.information(self, "Batch complete", msg)

