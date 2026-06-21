import sys
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QDragEnterEvent, QDropEvent, QAction
from PyQt6.QtWidgets import QApplication, QMainWindow, QStatusBar, QLabel, QTabWidget
from .crop_tab import CropTab
from .generate_tab import GenerateTab
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Crop & Compress")
        self.setMinimumSize(900, 650)
        self.resize(1100, 800)
        self.setAcceptDrops(True)

        # ── Status bar (shared) ──────────────────────────────────────────
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        
        self.status_stats_label = QLabel("")
        self.status.addPermanentWidget(self.status_stats_label)
        
        self.status.showMessage("Ready — select or drag images to get started")

        # ── Tab widget ───────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setDocumentMode(False)
        self.setCentralWidget(self.tabs)
        
        # Create tabs
        self.crop_tab = CropTab(self)
        self.generate_tab = GenerateTab(self)
        
        self.tabs.addTab(self.crop_tab, "✂  Crop && Compress")
        self.tabs.addTab(self.generate_tab, "✨  Generate")
        
        self.tabs.currentChanged.connect(self._on_tab_changed)
        
        self._create_menu_bar()
        
        # Globally intercept keys when active/focused
        QApplication.instance().installEventFilter(self)

    def closeEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        super().closeEvent(event)

    def _on_tab_changed(self, idx):
        if idx == 0:
            self.setWindowTitle("Crop & Compress")
            if self.crop_tab.files:
                self.crop_tab._update_status_bar()
            else:
                self.status_stats_label.setText("")
                self.status.showMessage("Ready — select or drag images to get started")
        else:
            self.setWindowTitle("Crop & Compress — Generate")
            self.status_stats_label.setText("")
            
            # Auto-sync references from crop_tab
            crop_files = set(self.crop_tab.files)
            gen_files = set(self.generate_tab.reference_paths)
            
            # Only auto-sync if we don't have any references that are outside of crop_tab.files
            if not (gen_files - crop_files):
                included_crop_files = [
                    f for i, f in enumerate(self.crop_tab.files)
                    if self.crop_tab.included[i]
                ]
                self.generate_tab.reference_paths = included_crop_files.copy()
                self.generate_tab._rebuild_thumbnails()
            
            ref_count = len(self.generate_tab.reference_paths)
            if ref_count:
                self.status.showMessage(f"{ref_count} reference image(s) loaded")
            else:
                self.status.showMessage("Add style reference images and a prompt to generate")

    def _create_menu_bar(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        open_action = QAction("Open Files…", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._menu_open_files)
        file_menu.addAction(open_action)
        
        out_action = QAction("Set Output Folder…", self)
        out_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        out_action.triggered.connect(self._menu_set_output)
        file_menu.addAction(out_action)
        
        file_menu.addSeparator()
        
        export_curr_action = QAction("Export Current Image", self)
        export_curr_action.setShortcut(QKeySequence("Ctrl+E"))
        export_curr_action.triggered.connect(self.crop_tab._apply_current)
        file_menu.addAction(export_curr_action)
        
        export_all_action = QAction("Export All Included", self)
        export_all_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
        export_all_action.triggered.connect(self.crop_tab._apply_all)
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
        reset_action.triggered.connect(self.crop_tab.canvas.clear_crop)
        edit_menu.addAction(reset_action)
        
        edit_menu.addSeparator()
        
        include_all_action = QAction("Include All Images", self)
        include_all_action.triggered.connect(self.crop_tab._include_all)
        edit_menu.addAction(include_all_action)
        
        exclude_all_action = QAction("Exclude All Images", self)
        exclude_all_action.triggered.connect(self.crop_tab._exclude_all)
        edit_menu.addAction(exclude_all_action)
        
        # Navigate menu
        nav_menu = menubar.addMenu("Navigate")
        
        prev_action = QAction("Previous Image", self)
        prev_action.setShortcut(QKeySequence(Qt.Key.Key_Left))
        prev_action.triggered.connect(self.crop_tab._prev)
        nav_menu.addAction(prev_action)
        
        next_action = QAction("Next Image", self)
        next_action.setShortcut(QKeySequence(Qt.Key.Key_Right))
        next_action.triggered.connect(self.crop_tab._next)
        nav_menu.addAction(next_action)
        
        # View menu (tab switching)
        view_menu = menubar.addMenu("View")
        
        tab_crop_action = QAction("Crop && Compress", self)
        tab_crop_action.setShortcut(QKeySequence("Ctrl+1"))
        tab_crop_action.triggered.connect(lambda: self.tabs.setCurrentIndex(0))
        view_menu.addAction(tab_crop_action)
        
        tab_gen_action = QAction("Generate", self)
        tab_gen_action.setShortcut(QKeySequence("Ctrl+2"))
        tab_gen_action.triggered.connect(lambda: self.tabs.setCurrentIndex(1))
        view_menu.addAction(tab_gen_action)

    def _select_all_noop(self):
        pass

    def _menu_open_files(self):
        if self.tabs.currentIndex() == 0:
            self.crop_tab._pick_files()
        else:
            self.generate_tab._add_references()
    
    def _menu_set_output(self):
        if self.tabs.currentIndex() == 0:
            self.crop_tab._pick_output()
        else:
            self.generate_tab._pick_output()

    # ── Global Key Interceptor ───────────────────────────────────────────

    def eventFilter(self, watched, event):
        if event.type() == event.Type.KeyPress:
            # If a modal dialog is open (like file picker or message box), let it handle the keys
            if QApplication.activeModalWidget() is not None:
                return super().eventFilter(watched, event)
            
            # Only intercept nav/crop keys when on the Crop tab
            if self.tabs.currentIndex() == 0:
                key = event.key()
                if key == Qt.Key.Key_Left:
                    self.crop_tab._prev()
                    return True
                elif key == Qt.Key.Key_Right:
                    self.crop_tab._next()
                    return True
                elif key == Qt.Key.Key_Space:
                    self.crop_tab._toggle_included()
                    return True
                elif key == Qt.Key.Key_Escape:
                    self.crop_tab.canvas.clear_crop()
                    return True
                    
        return super().eventFilter(watched, event)

    # ── Drag & drop routing ──────────────────────────────────────────────

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        # Route to the active tab
        current = self.tabs.currentWidget()
        if current:
            current.dropEvent(e)


# ─────────────────────────────────────────────────────────────────────────────
# Entry
# ─────────────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Crop & Compress")

    win = MainWindow()
    win.show()
    sys.exit(app.exec())
