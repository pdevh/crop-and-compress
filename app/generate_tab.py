import os
import mimetypes
from datetime import datetime
from pathlib import Path
import logging
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, 
    QMessageBox, QSizePolicy, QScrollArea, QGroupBox, QComboBox, QTextEdit, QFrame,
    QInputDialog, QLineEdit
)
from .openai_worker import (
    OpenAIWorker,
    DEFAULT_SYSTEM_PROMPT,
    MAX_REFERENCE_IMAGES,
    estimate_generation_cost,
    format_cost_estimate,
    get_env_path,
    output_size_for_aspect_ratio,
)
from .widgets import ReferenceThumbnail, SkeletonWidget

logger = logging.getLogger("CropAndCompress.GenerateTab")

class GenerateTab(QWidget):
    """AI image generation tab — uses cropped images as style references."""
    
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.setAcceptDrops(True)
        
        self.reference_paths: list[Path] = []
        self.output_dir: Path | None = None
        self.generated_images: list[tuple[bytes, str]] = []  # (data, mime_type)
        self._current_result_idx = 0
        self._worker: OpenAIWorker | None = None
        self._text_response = ""
        
        self._build_ui()
    
    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)
        
        # ── Left panel: inputs ───────────────────────────────────────────
        left_panel = QVBoxLayout()
        left_panel.setSpacing(10)
        
        # Reference images section
        ref_group = QGroupBox("Style Reference Images")

        ref_layout = QVBoxLayout(ref_group)
        
        # Scrollable thumbnail area
        self._ref_scroll = QScrollArea()
        self._ref_scroll.setWidgetResizable(True)
        self._ref_scroll.setMinimumHeight(160)
        self._ref_scroll.setMaximumHeight(200)

        
        self._ref_container = QWidget()
        self._ref_flow_layout = QHBoxLayout(self._ref_container)
        self._ref_flow_layout.setContentsMargins(8, 8, 8, 8)
        self._ref_flow_layout.setSpacing(8)
        self._ref_flow_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        # Placeholder label shown when no images
        self._ref_placeholder = QLabel("📂  Drag & drop images here, or click 'Add Images…'")
        self._ref_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ref_placeholder.setStyleSheet("color: #777; font-size: 12px; border: none;")
        self._ref_flow_layout.addWidget(self._ref_placeholder)
        
        self._ref_scroll.setWidget(self._ref_container)
        ref_layout.addWidget(self._ref_scroll)
        
        # Add / Clear buttons
        ref_btns = QHBoxLayout()
        btn_add = QPushButton("📂 Add Images…")
        btn_add.clicked.connect(self._add_references)
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        ref_btns.addWidget(btn_add)
        
        btn_clear = QPushButton("✕ Clear All")
        btn_clear.clicked.connect(self._clear_references)
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.setStyleSheet("color: #ff6666;")
        ref_btns.addWidget(btn_clear)
        ref_btns.addStretch()
        
        self._ref_count_label = QLabel("0 images")
        self._ref_count_label.setStyleSheet("color: #888;")
        ref_btns.addWidget(self._ref_count_label)
        
        ref_layout.addLayout(ref_btns)
        left_panel.addWidget(ref_group)
        
        # Prompt section
        prompt_group = QGroupBox("Prompt")

        prompt_layout = QVBoxLayout(prompt_group)
        
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlainText(DEFAULT_SYSTEM_PROMPT + "\n\n")
        self.prompt_edit.setMinimumHeight(150)
        self.prompt_edit.setMaximumHeight(200)
        self.prompt_edit.textChanged.connect(self._update_cost_estimate)

        prompt_layout.addWidget(self.prompt_edit)
        left_panel.addWidget(prompt_group)
        

        # Settings row
        settings_row = QHBoxLayout()
        
        # Aspect ratio
        ar_group = QGroupBox("Aspect Ratio")
        ar_layout = QHBoxLayout(ar_group)
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(["1:1", "3:4", "4:3", "9:16", "16:9"])
        self.aspect_combo.setCurrentText("3:4")
        self.aspect_combo.currentTextChanged.connect(self._update_cost_estimate)
        ar_layout.addWidget(self.aspect_combo)
        settings_row.addWidget(ar_group)
        
        # Resolution tier
        res_group = QGroupBox("Resolution")
        res_layout = QHBoxLayout(res_group)
        self.res_combo = QComboBox()
        self.res_combo.addItems(["1K", "2K", "4K"])
        self.res_combo.setCurrentText("1K")
        self.res_combo.currentTextChanged.connect(self._update_cost_estimate)
        res_layout.addWidget(self.res_combo)
        settings_row.addWidget(res_group)
        
        # Output folder
        out_group = QGroupBox("Output Folder")
        out_layout = QHBoxLayout(out_group)
        btn_out = QPushButton("📁 Folder…")
        btn_out.clicked.connect(self._pick_output)
        out_layout.addWidget(btn_out)
        self.out_label = QLabel("(not set)")
        self.out_label.setStyleSheet("color: rgba(255,255,255,0.5);")
        out_layout.addWidget(self.out_label, 1)
        settings_row.addWidget(out_group, 1)
        
        left_panel.addLayout(settings_row)
        
        # Generate button
        self.generate_btn = QPushButton("✨ Generate")
        self.generate_btn.setMinimumHeight(44)
        self.generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        f = self.generate_btn.font()
        f.setBold(True)
        self.generate_btn.setFont(f)
        self.generate_btn.clicked.connect(self._generate)
        left_panel.addWidget(self.generate_btn)
        
        # Cancel button (hidden by default)
        self.cancel_btn = QPushButton("✕ Cancel")
        self.cancel_btn.setMinimumHeight(44)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.cancel_btn.clicked.connect(self._cancel_generation)
        self.cancel_btn.setVisible(False)
        left_panel.addWidget(self.cancel_btn)

        self._cost_estimate_label = QLabel("")
        self._cost_estimate_label.setStyleSheet("color: #888; font-size: 12px;")
        self._cost_estimate_label.setWordWrap(True)
        left_panel.addWidget(self._cost_estimate_label)
        
        left_panel.addStretch()
        
        left_widget = QWidget()
        left_widget.setLayout(left_panel)
        left_widget.setMinimumWidth(340)
        left_widget.setMaximumWidth(480)
        main_layout.addWidget(left_widget)
        
        # ── Right panel: result preview ──────────────────────────────────
        right_panel = QVBoxLayout()
        right_panel.setSpacing(8)
        
        # Result area (stacked: skeleton / result image)
        self._result_frame = QFrame()

        result_frame_layout = QVBoxLayout(self._result_frame)
        result_frame_layout.setContentsMargins(0, 0, 0, 0)
        
        # Skeleton placeholder
        self._skeleton = SkeletonWidget()
        self._skeleton.setVisible(False)
        result_frame_layout.addWidget(self._skeleton)
        
        # Result image label
        self._result_label = QLabel()
        self._result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._result_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._result_label.setStyleSheet("border: none; color: #555; font-size: 14px;")
        self._result_label.setText("Generated image will appear here")
        result_frame_layout.addWidget(self._result_label)
        
        right_panel.addWidget(self._result_frame, 1)
        
        # Text response (if any)
        self._text_response_label = QLabel("")
        self._text_response_label.setWordWrap(True)
        self._text_response_label.setStyleSheet("color: #aaa; font-size: 12px; padding: 4px 8px;")
        self._text_response_label.setVisible(False)
        right_panel.addWidget(self._text_response_label)
        
        # Result actions bar
        result_bar = QHBoxLayout()
        
        self.save_btn = QPushButton("💾 Save Image")
        self.save_btn.setEnabled(False)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.save_btn.clicked.connect(self._save_result)
        result_bar.addWidget(self.save_btn)
        
        self._result_info = QLabel("")
        self._result_info.setStyleSheet("color: #888; font-size: 12px;")
        result_bar.addWidget(self._result_info, 1)
        
        right_panel.addLayout(result_bar)
        
        main_layout.addLayout(right_panel, 1)
        self._update_cost_estimate()
    

    
    # ── Reference image management ───────────────────────────────────────
    
    def _add_references(self):
        start_dir = ""
        if hasattr(self.parent_window, "crop_tab") and self.parent_window.crop_tab.files:
            start_dir = str(self.parent_window.crop_tab.files[0].parent)
            
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select reference images", start_dir,
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tiff *.tif)"
        )
        if paths:
            for p in paths:
                pp = Path(p)
                if pp not in self.reference_paths:
                    self.reference_paths.append(pp)
            self._rebuild_thumbnails()
    
    def _clear_references(self):
        self.reference_paths.clear()
        self._rebuild_thumbnails()
    
    def _remove_reference(self, thumb: ReferenceThumbnail):
        if thumb.path in self.reference_paths:
            self.reference_paths.remove(thumb.path)
        self._rebuild_thumbnails()
    
    def _rebuild_thumbnails(self):
        # Remove all existing widgets
        while self._ref_flow_layout.count():
            item = self._ref_flow_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self.reference_paths:
            self._ref_placeholder = QLabel("📂  Drag & drop images here, or click 'Add Images…'")
            self._ref_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._ref_placeholder.setStyleSheet("color: #777; font-size: 12px; border: none;")
            self._ref_flow_layout.addWidget(self._ref_placeholder)
        else:
            for path in self.reference_paths:
                thumb = ReferenceThumbnail(path)
                thumb.removed.connect(self._remove_reference)
                self._ref_flow_layout.addWidget(thumb)
        
        self._ref_count_label.setText(f"{len(self.reference_paths)} image{'s' if len(self.reference_paths) != 1 else ''}")
        self._update_cost_estimate()

    def _update_cost_estimate(self):
        if not hasattr(self, "_cost_estimate_label"):
            return

        prompt = self.prompt_edit.toPlainText().strip()
        aspect_ratio = self.aspect_combo.currentText()
        resolution = self.res_combo.currentText()
        output_size = output_size_for_aspect_ratio(aspect_ratio, resolution)
        estimate = estimate_generation_cost(
            prompt=prompt,
            image_paths=list(self.reference_paths),
            output_size=output_size,
        )
        self._cost_estimate_label.setText(
            f"{format_cost_estimate(estimate)} • output {output_size}"
        )
    
    # ── Drag & drop for references ───────────────────────────────────────
    
    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
    
    def dropEvent(self, e: QDropEvent):
        urls = e.mimeData().urls()
        exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}
        for u in urls:
            p = Path(u.toLocalFile())
            if p.is_dir():
                for child in sorted(p.iterdir(), key=lambda x: x.name.lower()):
                    if child.is_file() and child.suffix.lower() in exts and child not in self.reference_paths:
                        self.reference_paths.append(child)
            elif p.is_file() and p.suffix.lower() in exts and p not in self.reference_paths:
                self.reference_paths.append(p)
        self._rebuild_thumbnails()
    
    # ── Output folder ────────────────────────────────────────────────────
    
    def _pick_output(self):
        d = QFileDialog.getExistingDirectory(self, "Choose output folder for generated images")
        if d:
            self.output_dir = Path(d)
            self.out_label.setText(self.output_dir.name)
    
    def _ensure_output(self) -> bool:
        if self.output_dir and self.output_dir.is_dir():
            return True
        d = QFileDialog.getExistingDirectory(self, "Choose output folder for generated images")
        if not d:
            return False
        self.output_dir = Path(d)
        self.out_label.setText(self.output_dir.name)
        return True
    
    # ── Generation ───────────────────────────────────────────────────────
    
    def _generate(self):
        prompt = self.prompt_edit.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "Missing prompt", "Please enter a text prompt.")
            return
        
        logger.info(f"Initiating generation. Prompt: '{prompt[:60]}...' ({len(prompt)} chars)")
        logger.info(f"References selected: {[str(p) for p in self.reference_paths]}")

        if len(self.reference_paths) > MAX_REFERENCE_IMAGES:
            QMessageBox.warning(
                self,
                "Too many references",
                f"GPT Image 2 supports up to {MAX_REFERENCE_IMAGES} reference images. "
                f"Remove {len(self.reference_paths) - MAX_REFERENCE_IMAGES} image(s) and try again."
            )
            return
        
        if not self.reference_paths:
            reply = QMessageBox.question(
                self, "No reference images",
                "No style reference images selected. Generate without references?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                logger.info("Generation aborted by user due to lack of references.")
                return
        
        aspect_ratio = self.aspect_combo.currentText()
        resolution = self.res_combo.currentText()
        output_size = output_size_for_aspect_ratio(aspect_ratio, resolution)
        estimate = estimate_generation_cost(
            prompt=prompt,
            image_paths=list(self.reference_paths),
            output_size=output_size,
        )
        self._cost_estimate_label.setText(
            f"{format_cost_estimate(estimate)} • output {output_size}"
        )
        
        # Check API key before starting worker
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            logger.info("OPENAI_API_KEY not found in environment, requesting from user.")
            key, ok = QInputDialog.getText(
                self, "API Key Required",
                "Please enter your OpenAI API Key.\nIt will be saved locally so you don't have to enter it again.",
                QLineEdit.EchoMode.Password
            )
            if ok and key.strip():
                api_key = key.strip()
                os.environ["OPENAI_API_KEY"] = api_key
                env_path = get_env_path()
                logger.info(f"Saving API key to env file at {env_path}")
                
                key_exists = False
                env_text = ""
                if env_path.exists():
                    try:
                        with open(env_path, "r", encoding="utf-8") as f:
                            env_text = f.read()
                            if "OPENAI_API_KEY" in env_text:
                                key_exists = True
                    except Exception as e:
                        logger.error(f"Error reading env file: {e}")
                
                try:
                    if key_exists:
                        lines = []
                        for line in env_text.splitlines():
                            if line.startswith("OPENAI_API_KEY="):
                                lines.append(f"OPENAI_API_KEY={api_key}")
                            else:
                                lines.append(line)
                        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    else:
                        # Ensure we start on a new line if the file doesn't end with one
                        prefix = "\n" if env_path.exists() and env_path.stat().st_size > 0 else ""
                        with open(env_path, "a", encoding="utf-8") as f:
                            f.write(f"{prefix}OPENAI_API_KEY={api_key}\n")
                    logger.info("Saved API key successfully.")
                except Exception as e:
                    logger.error(f"Could not save API key to {env_path}: {e}")
                    print(f"Warning: Could not save API key to {env_path}: {e}")
            else:
                logger.info("Generation cancelled because user did not provide an API key.")
                return  # User cancelled
        
        # Clear previous results
        self.generated_images.clear()
        self._text_response = ""
        self._text_response_label.setVisible(False)
        self._text_response_label.setText("")
        self._current_result_idx = 0
        
        # Switch to loading state
        self._result_label.setVisible(False)
        self._skeleton.setVisible(True)
        self._skeleton.start()
        self.generate_btn.setVisible(False)
        self.cancel_btn.setVisible(True)
        self.save_btn.setEnabled(False)
        self._result_info.setText("")
        
        self.parent_window.status.showMessage("⏳ Generating image…")
        
        # Launch worker
        logger.info("Starting OpenAIWorker background thread...")
        self._worker = OpenAIWorker(
            prompt=prompt,
            image_paths=list(self.reference_paths),
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )
        self._worker.image_ready.connect(self._on_image_ready)
        self._worker.text_chunk.connect(self._on_text_chunk)
        self._worker.error.connect(self._on_error)
        self._worker.finished_signal.connect(self._on_finished)
        self._worker.start()
    
    def _cancel_generation(self):
        logger.info("User clicked cancel generation")
        if self._worker:
            self._worker.cancel()
        self._reset_ui_after_generation()
        self.parent_window.status.showMessage("Generation cancelled")
    
    def _on_image_ready(self, data: bytes, mime_type: str):
        logger.info(f"Image received in main thread. Mime-type: {mime_type}, bytes: {len(data)}")
        self.generated_images.append((data, mime_type))
        
        # Show the image in the result area
        self._skeleton.stop()
        self._skeleton.setVisible(False)
        self._result_label.setVisible(True)
        
        pm = QPixmap()
        pm.loadFromData(data)
        if not pm.isNull():
            # Scale to fit result area
            available = self._result_label.size()
            scaled = pm.scaled(
                available,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self._result_label.setPixmap(scaled)
            self._result_info.setText(f"Generated: {pm.width()}×{pm.height()}")
            logger.debug(f"Rendered image: {pm.width()}x{pm.height()}")
        else:
            logger.error("Failed to load QPixmap from raw image bytes!")
            self._result_label.setText("⚠️ Failed to render generated image")
        
        self.save_btn.setEnabled(True)
        
        if self.output_dir and self.output_dir.is_dir():
            self._save_result()
    
    def _on_text_chunk(self, text: str):
        logger.debug(f"Text response chunk: '{text}'")
        self._text_response += text
        self._text_response_label.setText(self._text_response)
        self._text_response_label.setVisible(True)
    
    def _on_error(self, msg: str):
        logger.error(f"Generation error received in main thread: {msg}")
        self._reset_ui_after_generation()
        self._result_label.setText(f"⚠️ Error")
        self._result_label.setVisible(True)
        QMessageBox.critical(self, "Generation Error", msg)
        self.parent_window.status.showMessage("Generation failed")
    
    def _on_finished(self):
        logger.info("Worker finished signal received in main thread")
        self._reset_ui_after_generation()
        if self.generated_images:
            self.parent_window.status.showMessage(
                f"✨ Generated {len(self.generated_images)} image(s)"
            )
    
    def _reset_ui_after_generation(self):
        logger.debug("Resetting UI after generation")
        self._skeleton.stop()
        self._skeleton.setVisible(False)
        self._result_label.setVisible(True)
        self.generate_btn.setVisible(True)
        self.cancel_btn.setVisible(False)
        self._worker = None
    
    # ── Save result ──────────────────────────────────────────────────────
    
    def _save_result(self):
        if not self.generated_images:
            logger.warning("Attempted to save result but no generated images exist")
            return
        
        if not self._ensure_output():
            logger.info("User aborted choosing an output folder for saving results")
            return
        
        data, mime_type = self.generated_images[self._current_result_idx]
        ext = mimetypes.guess_extension(mime_type) or ".png"
        # Fix .jpe → .jpg
        if ext == ".jpe":
            ext = ".jpg"
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"motif_{timestamp}{ext}"
        out_path = self.output_dir / filename
        
        # Avoid collisions
        counter = 2
        while out_path.exists():
            out_path = self.output_dir / f"motif_{timestamp}_{counter}{ext}"
            counter += 1
        
        logger.info(f"Saving generated image to: {out_path}")
        try:
            with open(out_path, "wb") as f:
                f.write(data)
            
            sz = out_path.stat().st_size / 1024
            self.parent_window.status.showMessage(f"✓ Saved {out_path.name}  ({sz:.0f} KB)")
            self._result_info.setText(f"Saved → {out_path.name}")
            logger.info(f"Successfully saved image {out_path.name} ({sz:.1f} KB)")
        except Exception as e:
            logger.exception("Failed to write/save generated image to disk")
            QMessageBox.critical(self, "Save Error", f"Could not save image: {e}")
    
    # ── Handle resize to re-scale preview ────────────────────────────────
    
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.generated_images and self._result_label.pixmap() and not self._result_label.pixmap().isNull():
            # Reload from raw data to re-scale
            data, _ = self.generated_images[self._current_result_idx]
            pm = QPixmap()
            pm.loadFromData(data)
            if not pm.isNull():
                available = self._result_label.size()
                scaled = pm.scaled(
                    available,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self._result_label.setPixmap(scaled)
