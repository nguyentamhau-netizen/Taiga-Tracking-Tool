from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import threading
import traceback
import webbrowser

import uvicorn


LOG_PATH = Path(sys.executable).resolve().parent / "portable-runtime.log" if getattr(sys, "frozen", False) else Path(__file__).resolve().parent / "portable-runtime.log"


def _log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as stream:
        stream.write(f"[{timestamp}] {message}\n")


def _open_browser() -> None:
    webbrowser.open("http://127.0.0.1:8000")


if __name__ == "__main__":
    try:
        _log("Starting portable app")
        from app.main import app
        threading.Timer(2.0, _open_browser).start()
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning", log_config=None, access_log=False)
    except Exception as exc:  # pragma: no cover - runtime fallback for portable builds
        _log(f"Portable startup failed: {exc!r}")
        _log(traceback.format_exc())
        raise
