---
trigger: always_on
---

## 1. Never Create Qt GUI Objects Outside the Main Thread

Qt **will call `abort()`** if any `QWidget`, `QMessageBox`, `QDialog`, or similar GUI object is instantiated or executed from a background thread (`QThread`, `threading.Thread`, etc.).

### Rules

- **All UI creation and manipulation must happen on the main thread.** No exceptions.
- If a background thread needs to communicate a result or error to the UI, it **must** use a `pyqtSignal` and let the main-thread slot handle the widget work.
- In `sys.excepthook` and any other global error handler, **always guard** with `threading.current_thread() is threading.main_thread()` before touching any Qt widget.
- If you need to show an error dialog from a background context, emit a signal or use `QMetaObject.invokeMethod` with `Qt.ConnectionType.QueuedConnection` to schedule it on the main thread.

### Bad

```python
# Inside a QThread.run() or sys.excepthook called from a worker thread:
msg_box = QMessageBox()  # FATAL — triggers qFatal() → abort()
msg_box.exec()
```

### Good

```python
# In sys.excepthook:
if threading.current_thread() is not threading.main_thread():
    logger.critical("Uncaught exception on background thread", exc_info=...)
    return  # Do NOT touch Qt widgets

# In a QThread subclass — emit a signal, let the main thread handle UI:
self.error.emit(f"Something went wrong: {e}")
```

---

## 2. Catch Broad Exceptions When Importing in Background Threads

When lazily importing third-party SDKs (e.g., `google.genai`, `pydantic`) inside a `QThread.run()` method, **never catch only `ImportError`**. In PyInstaller-bundled apps (especially macOS `--windowed` mode), sub-dependencies can throw `AttributeError`, `ValueError`, `TypeError`, or other non-`ImportError` exceptions during initialization (e.g., because `sys.stdout` is `None`).

### Rules

- Use `except Exception` (not `except ImportError`) when importing inside background threads.
- Always emit the error via a signal so the user gets feedback instead of a silent crash.
- Always call the `finished_signal` and `return` after emitting the error so the thread exits cleanly.

### Bad

```python
try:
    from google import genai
except ImportError as e:  # Misses AttributeError, ValueError, etc.
    self.error.emit("Package not installed")
```

### Good

```python
try:
    from google import genai
    from google.genai import types
except Exception as e:
    logger.exception(f"Failed to import SDK: {e}")
    self.error.emit(f"Could not load the AI engine.\nError: {e}")
    self.finished_signal.emit()
    return
```

---

## 3. PyInstaller Bundling Awareness

This app is distributed as a frozen PyInstaller `.app` bundle on macOS.

- **`sys.stdout` / `sys.stderr` may be `None`** in `--windowed` mode. Never assume they exist. Use `sys.stderr` with a guard or log to file exclusively.
- **Hidden imports matter.** If a new SDK dependency is added, check whether PyInstaller picks up all its sub-modules. Add `--hidden-import` or `--collect-all` flags in `build.sh` / the `.spec` file as needed.
- **Path resolution differs when frozen.** Use `getattr(sys, 'frozen', False)` checks and `sys.executable` for path resolution, not `__file__`.

---

## 4. General QThread Discipline

- Every `QThread.run()` method must have a top-level `try/except Exception` that emits errors via signals. Unhandled exceptions escaping `run()` go to `sys.excepthook`, which is dangerous (see Rule 1).
- Always emit `finished_signal` in a `finally` block so the UI never gets stuck in a "loading" state.
- Use `self._cancelled` flags checked at safe points — never call `QThread.terminate()`.
