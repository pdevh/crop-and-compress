import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import platform
import traceback
import threading
from PyQt6.QtWidgets import QMessageBox, QApplication

logger = logging.getLogger("CropAndCompress")
logger.propagate = False

def get_log_file_path() -> Path:
    log_dir = Path.home() / ".crop_and_compress"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "crop_and_compress.log"

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
        
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    
    # Only show QMessageBox if we are on the main thread —
    # Qt will abort() if GUI objects are created from a background thread.
    if threading.current_thread() is not threading.main_thread():
        return
    
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    
    app = QApplication.instance()
    if app:
        try:
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.Critical)
            msg_box.setWindowTitle("Application Error")
            msg_box.setText("An unexpected crash or error occurred.")
            msg_box.setInformativeText(str(exc_value))
            msg_box.setDetailedText(tb_text)
            msg_box.exec()
        except Exception as e:
            logger.error(f"Failed to display crash QMessageBox: {e}")

def handle_thread_exception(args):
    logger.critical(
        f"Uncaught thread exception in thread {args.thread.name}:",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback)
    )

def setup_logging():
    log_file = get_log_file_path()
    
    # Root logger config
    logging.basicConfig(level=logging.INFO)
    
    # App logger level
    logger.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] (%(threadName)s) %(name)s.%(funcName)s:%(lineno)d - %(message)s"
    )
    
    # Rotating File Handler (5 MB per file, max 3 files)
    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console Handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Exception hooks
    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception
    
    logger.info("=== Logging Initialized ===")
    logger.info(f"Log file: {log_file}")
    logger.info(f"OS: {platform.system()} {platform.release()} ({platform.machine()})")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Frozen: {getattr(sys, 'frozen', False)}")
    logger.info(f"Executable: {sys.executable}")
