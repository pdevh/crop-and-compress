from enum import Enum, auto
from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor
from PyQt6.QtWidgets import QLabel, QSizePolicy
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


