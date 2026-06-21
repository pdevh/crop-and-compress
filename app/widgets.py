from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRect
from PyQt6.QtGui import QPixmap, QPainter, QColor
from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy
class ReferenceThumbnail(QFrame):
    """A single reference image thumbnail with a remove button."""
    
    removed = pyqtSignal(object)  # emits self
    
    THUMB_SIZE = 120
    
    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        self.setFixedSize(self.THUMB_SIZE + 8, self.THUMB_SIZE + 28)
        self.setStyleSheet("""
            ReferenceThumbnail {
                background: #2a2a2a;
                border: 1px solid #444;
                border-radius: 8px;
            }
            ReferenceThumbnail:hover {
                border-color: #00ff88;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        
        # Thumbnail image
        thumb_label = QLabel()
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_label.setFixedSize(self.THUMB_SIZE, self.THUMB_SIZE)
        thumb_label.setStyleSheet("background: #1a1a1a; border-radius: 4px; border: none;")
        
        pm = QPixmap(str(path))
        if not pm.isNull():
            pm = pm.scaled(
                self.THUMB_SIZE - 4, self.THUMB_SIZE - 4,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        thumb_label.setPixmap(pm)
        layout.addWidget(thumb_label)
        
        # Filename + remove
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        
        name_label = QLabel(path.name)
        name_label.setStyleSheet("color: #aaa; font-size: 9px; border: none;")
        name_label.setMaximumWidth(self.THUMB_SIZE - 20)
        bottom.addWidget(name_label, 1)
        
        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(18, 18)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: #553333; color: #ff6666; border: none;
                border-radius: 9px; font-size: 11px; font-weight: bold;
            }
            QPushButton:hover { background: #ff4444; color: white; }
        """)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.clicked.connect(lambda: self.removed.emit(self))
        bottom.addWidget(remove_btn)
        
        layout.addLayout(bottom)


# ─────────────────────────────────────────────────────────────────────────────
# Skeleton / shimmer placeholder for loading state
# ─────────────────────────────────────────────────────────────────────────────

class SkeletonWidget(QWidget):
    """Animated shimmer placeholder shown while generating."""
    
    def __init__(self):
        super().__init__()
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._phase = 0.0
        
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
    
    def start(self):
        self._phase = 0.0
        self._timer.start(30)  # ~33 fps
    
    def stop(self):
        self._timer.stop()
    
    def _tick(self):
        self._phase += 0.02
        if self._phase > 2.0:
            self._phase = 0.0
        self.update()
    
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w, h = self.width(), self.height()
        
        # Dark background
        p.fillRect(self.rect(), QColor("#1a1a1a"))
        
        # Draw skeleton shapes with shimmer
        rects = [
            # Main image placeholder (centered, large)
            QRect(int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.75)),
            # Text line placeholders
            QRect(int(w * 0.1), int(h * 0.84), int(w * 0.6), 12),
            QRect(int(w * 0.1), int(h * 0.88), int(w * 0.4), 12),
        ]
        
        for rect in rects:
            # Base color
            p.setBrush(QColor("#2a2a2a"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, 6, 6)
            
            # Shimmer highlight - moves across
            shimmer_x = (self._phase - 0.5) * (w + 200) - 100
            shimmer_width = 150
            
            # Clip to the rect and draw a gradient highlight
            p.save()
            p.setClipRect(rect)
            
            from PyQt6.QtGui import QLinearGradient
            grad = QLinearGradient(shimmer_x, 0, shimmer_x + shimmer_width, 0)
            grad.setColorAt(0.0, QColor(0, 0, 0, 0))
            grad.setColorAt(0.5, QColor(255, 255, 255, 25))
            grad.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setBrush(grad)
            p.drawRoundedRect(rect, 6, 6)
            p.restore()
        
        # "Generating…" text in center
        p.setPen(QColor("#666"))
        f = self.font()
        f.setPointSize(14)
        p.setFont(f)
        main_rect = rects[0]
        p.drawText(main_rect, Qt.AlignmentFlag.AlignCenter, "✨ Generating…")
        
        p.end()

