"""AutoScrcpy launcher: start the backend without any console window.

Explorer runs ``.pyw`` files with the GUI Python interpreter
(``pythonw.exe`` / ``pyw.exe``), so this launcher never owns a console.  It
starts ``app.py`` with the native Windows ``CREATE_NO_WINDOW`` flag (not
PowerShell's ``-WindowStyle Hidden``) and exits once the backend is running.
``start-debug.bat`` remains the console entry point for troubleshooting.
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "AutoScrcpy"
BASE_DIR = Path(__file__).resolve().parent
APP_SCRIPT = BASE_DIR / "app.py"
LOG_PATH = "%LOCALAPPDATA%\\AutoScrcpy\\autoscrcpy.log"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# Keep the launcher around long enough to catch import/config failures.  If
# app.py is still running after this, it has started successfully.
STARTUP_GRACE = 2.0


def show_error(message: str) -> None:
    """``pythonw`` has no console, so failures need a native message box."""
    if os.name == "nt":
        try:
            ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10)
            return
        except Exception:
            pass
    with contextlib.suppress(Exception):
        print(f"{APP_NAME}: {message}", file=sys.stderr)


def pythonw_executable(executable: str | None = None) -> Path | None:
    """Return the GUI interpreter to start the backend with.

    ``pythonw`` from PATH is preferred so the launcher uses the same
    interpreter as ``start-debug.bat`` and ``install-dependencies.bat``.
    Double-clicking a ``.pyw`` normally means ``sys.executable`` already is
    ``pythonw.exe``; that is the fallback when PATH has no ``pythonw``.  A plain
    ``python.exe`` also works because ``CREATE_NO_WINDOW`` hides its console.
    """
    found = shutil.which("pythonw")
    if found:
        return Path(found)
    raw = sys.executable if executable is None else executable
    current = Path(raw) if raw else None
    if current is not None and current.is_file():
        if current.name.lower() == "pythonw.exe":
            return current
        gui = current.with_name("pythonw.exe")
        if gui.is_file():
            return gui
        return current
    found = shutil.which("python")
    return Path(found) if found else None


def build_command(
    executable: Path, script: Path, args: list[str] | None = None
) -> list[str]:
    return [str(executable), str(script), *(args or [])]


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if not APP_SCRIPT.is_file():
        show_error("找不到 app.py。\n\n请保持 launch.pyw 与 app.py 在同一个文件夹中。")
        return 1

    executable = pythonw_executable()
    if executable is None:
        show_error(
            "启动失败：找不到 pythonw.exe。\n\n"
            "请安装 Python 并加入 PATH，或双击 start-debug.bat 查看详细错误。"
        )
        return 1

    try:
        process = subprocess.Popen(
            build_command(executable, APP_SCRIPT, args),
            cwd=str(BASE_DIR),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            close_fds=True,
        )
    except OSError as exc:
        show_error(
            f"启动失败：{exc}\n\n"
            "请安装 Python 并加入 PATH，或双击 start-debug.bat 查看详细错误。"
        )
        return 1

    try:
        code = process.wait(timeout=STARTUP_GRACE)
    except subprocess.TimeoutExpired:
        # The backend is up; this launcher process can go away.
        return 0
    if code != 0:
        show_error(
            "AutoScrcpy 后端未能启动。\n\n"
            "请双击 start-debug.bat 查看错误，或检查日志：\n"
            f"{LOG_PATH}"
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
