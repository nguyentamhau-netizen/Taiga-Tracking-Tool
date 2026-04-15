from __future__ import annotations

from datetime import datetime
from pathlib import Path
import ctypes
import socket
import sys
import threading
import traceback
import webbrowser
from urllib.request import urlopen

import uvicorn


LOG_PATH = Path(sys.executable).resolve().parent / "portable-runtime.log" if getattr(sys, "frozen", False) else Path(__file__).resolve().parent / "portable-runtime.log"
URL_PATH = Path(sys.executable).resolve().parent / "portable-url.txt" if getattr(sys, "frozen", False) else Path(__file__).resolve().parent / "portable-url.txt"


def _log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as stream:
        stream.write(f"[{timestamp}] {message}\n")


def _show_error(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, message, "Taiga QC Tracker", 0x10)


def _find_open_port(preferred_port: int = 8000, attempts: int = 20) -> int:
    for port in range(preferred_port, preferred_port + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("Could not find a free local port.")


def _wait_for_server(url: str, timeout_seconds: int = 20) -> bool:
    deadline = datetime.now().timestamp() + timeout_seconds
    while datetime.now().timestamp() < deadline:
        try:
            with urlopen(f"{url}/api/health", timeout=2) as response:
                if response.status == 200:
                    return True
        except Exception:
            pass
        threading.Event().wait(0.5)
    return False


def _open_browser(url: str) -> None:
    if _wait_for_server(url):
        webbrowser.open(url)
        return
    _log(f"Server did not become ready at {url}")
    _show_error(
        f"Taiga QC Tracker could not start correctly.\n\n"
        f"Please open this log file and send it to support:\n{LOG_PATH}"
    )


if __name__ == "__main__":
    try:
        _log("Starting portable app")
        from app.main import app
        port = _find_open_port()
        base_url = f"http://127.0.0.1:{port}"
        URL_PATH.write_text(base_url, encoding="utf-8")
        _log(f"Using local URL: {base_url}")
        threading.Thread(target=_open_browser, args=(base_url,), daemon=True).start()
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", log_config=None, access_log=False)
    except Exception as exc:  # pragma: no cover - runtime fallback for portable builds
        _log(f"Portable startup failed: {exc!r}")
        _log(traceback.format_exc())
        _show_error(
            f"Taiga QC Tracker could not start.\n\n"
            f"Please open this log file and send it to support:\n{LOG_PATH}"
        )
        raise
