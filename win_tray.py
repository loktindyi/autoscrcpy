"""Win32 integration for AutoScrcpy: tray icon and window helpers.

The application deliberately keeps its runtime dependencies small, so the
notification-area icon is implemented directly on ``Shell_NotifyIconW`` with
``ctypes`` instead of pulling in a GUI toolkit.  Everything in this module is
a safe no-op outside Windows (``IS_WINDOWS`` is false), which keeps imports
and tests portable.
"""

from __future__ import annotations

import contextlib
import ctypes
import logging
import os
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Callable

LOGGER = logging.getLogger("autoscrcpy")

IS_WINDOWS = os.name == "nt"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# -- Win32 constants --------------------------------------------------------

WM_NULL = 0x0000
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_SETTINGCHANGE = 0x001A
WM_THEMECHANGED = 0x031A
WM_DPICHANGED = 0x02E0
WM_TIMER = 0x0113
WM_APP = 0x8000
WM_TRAY = WM_APP + 1
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205

# Explorer broadcasts the registered "TaskbarCreated" message every time it
# (re)creates the taskbar; the notification-area icon has to be added again.
TASKBAR_RESTORE_TIMER = 1
TASKBAR_RESTORE_INTERVAL_MS = 500
TASKBAR_RESTORE_MAX_ATTEMPTS = 24

GW_OWNER = 4

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NIIF_INFO = 0x00000001

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040
IDI_APPLICATION = 32512

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_GRAYED = 0x00000001
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080

SW_SHOWMINNOACTIVE = 7
SW_RESTORE = 9

SM_CXSMICON = 49
SM_CYSMICON = 50

MENU_OPEN = 1
MENU_STOP = 2
MENU_QUIT = 3

ERROR_CLASS_ALREADY_EXISTS = 1410


# -- ctypes plumbing --------------------------------------------------------

if IS_WINDOWS:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
else:  # pragma: no cover - the module is exercised on Windows in this repo
    _user32 = None
    _shell32 = None
    _kernel32 = None

_FUNCTYPE = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
WNDPROC = _FUNCTYPE(
    wintypes.LPARAM,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
WNDENUMPROC = _FUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HANDLE),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


def _bind_functions() -> None:
    """Declare prototypes so 64-bit handles are never truncated to ``int``."""
    if not IS_WINDOWS:
        return
    u = _user32
    u.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    u.RegisterClassW.restype = wintypes.WORD
    u.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
    u.UnregisterClassW.restype = wintypes.BOOL
    u.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HANDLE,
        wintypes.HINSTANCE,
        wintypes.LPVOID,
    ]
    u.CreateWindowExW.restype = wintypes.HWND
    u.DestroyWindow.argtypes = [wintypes.HWND]
    u.DestroyWindow.restype = wintypes.BOOL
    u.DefWindowProcW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    u.DefWindowProcW.restype = wintypes.LPARAM
    u.GetMessageW.argtypes = [
        ctypes.POINTER(MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
    ]
    u.GetMessageW.restype = ctypes.c_int
    u.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
    u.TranslateMessage.restype = wintypes.BOOL
    u.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    u.DispatchMessageW.restype = wintypes.LPARAM
    u.PostQuitMessage.argtypes = [ctypes.c_int]
    u.PostQuitMessage.restype = None
    u.LoadImageW.argtypes = [
        wintypes.HINSTANCE,
        wintypes.LPCWSTR,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    u.LoadImageW.restype = wintypes.HANDLE
    u.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
    u.LoadIconW.restype = wintypes.HICON
    u.DestroyIcon.argtypes = [wintypes.HICON]
    u.DestroyIcon.restype = wintypes.BOOL
    u.CreatePopupMenu.argtypes = []
    u.CreatePopupMenu.restype = wintypes.HANDLE
    u.DestroyMenu.argtypes = [wintypes.HANDLE]
    u.DestroyMenu.restype = wintypes.BOOL
    u.AppendMenuW.argtypes = [
        wintypes.HANDLE,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPCWSTR,
    ]
    u.AppendMenuW.restype = wintypes.BOOL
    u.TrackPopupMenu.argtypes = [
        wintypes.HANDLE,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        ctypes.c_void_p,
    ]
    u.TrackPopupMenu.restype = ctypes.c_int
    u.SetForegroundWindow.argtypes = [wintypes.HWND]
    u.SetForegroundWindow.restype = wintypes.BOOL
    u.SwitchToThisWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
    u.SwitchToThisWindow.restype = None
    u.GetForegroundWindow.argtypes = []
    u.GetForegroundWindow.restype = wintypes.HWND
    u.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    u.GetCursorPos.restype = wintypes.BOOL
    u.PostMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    u.PostMessageW.restype = wintypes.BOOL
    u.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    u.EnumWindows.restype = wintypes.BOOL
    u.IsWindow.argtypes = [wintypes.HWND]
    u.IsWindow.restype = wintypes.BOOL
    u.IsWindowVisible.argtypes = [wintypes.HWND]
    u.IsWindowVisible.restype = wintypes.BOOL
    u.IsIconic.argtypes = [wintypes.HWND]
    u.IsIconic.restype = wintypes.BOOL
    u.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    u.GetWindow.restype = wintypes.HWND
    u.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    u.GetWindowThreadProcessId.restype = wintypes.DWORD
    u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    u.GetWindowTextLengthW.restype = ctypes.c_int
    u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u.GetWindowTextW.restype = ctypes.c_int
    u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    u.GetClassNameW.restype = ctypes.c_int
    u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    u.ShowWindow.restype = wintypes.BOOL
    u.BringWindowToTop.argtypes = [wintypes.HWND]
    u.BringWindowToTop.restype = wintypes.BOOL
    u.SetFocus.argtypes = [wintypes.HWND]
    u.SetFocus.restype = wintypes.HWND
    u.AttachThreadInput.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.BOOL,
    ]
    u.AttachThreadInput.restype = wintypes.BOOL
    u.GetSystemMetrics.argtypes = [ctypes.c_int]
    u.GetSystemMetrics.restype = ctypes.c_int
    u.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
    u.RegisterWindowMessageW.restype = wintypes.UINT
    u.SetTimer.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
    ]
    u.SetTimer.restype = wintypes.UINT
    u.KillTimer.argtypes = [wintypes.HWND, wintypes.UINT]
    u.KillTimer.restype = wintypes.BOOL

    k = _kernel32
    k.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    k.GetModuleHandleW.restype = wintypes.HINSTANCE
    k.GetCurrentThreadId.argtypes = []
    k.GetCurrentThreadId.restype = wintypes.DWORD

    s = _shell32
    s.Shell_NotifyIconW.argtypes = [
        wintypes.DWORD,
        ctypes.POINTER(NOTIFYICONDATAW),
    ]
    s.Shell_NotifyIconW.restype = wintypes.BOOL


_bind_functions()


# -- Window discovery and manipulation --------------------------------------


def _visible_windows() -> list[tuple[int, int, str, str]]:
    """Return ``(hwnd, pid, title, class)`` for visible top-level windows."""
    if not IS_WINDOWS:
        return []
    results: list[tuple[int, int, str, str]] = []

    def callback(hwnd: int, _lparam: int) -> bool:
        try:
            if not _user32.IsWindowVisible(hwnd):
                return True
            if _user32.GetWindow(hwnd, GW_OWNER):
                return True
            pid = wintypes.DWORD(0)
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            length = _user32.GetWindowTextLengthW(hwnd)
            title = ctypes.create_unicode_buffer(max(1, length + 1))
            if length > 0:
                _user32.GetWindowTextW(hwnd, title, len(title))
            kind = ctypes.create_unicode_buffer(256)
            _user32.GetClassNameW(hwnd, kind, len(kind))
            results.append((int(hwnd), int(pid.value), title.value, kind.value))
        except Exception:  # pragma: no cover - defensive against odd windows
            LOGGER.debug("Could not inspect a window", exc_info=True)
        return True

    _user32.EnumWindows(WNDENUMPROC(callback), 0)
    return results


def window_process_id(hwnd: int) -> int:
    if not IS_WINDOWS or not hwnd:
        return 0
    pid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def find_console_window() -> int:
    """Find the chromeless Edge/Chrome window that hosts the UI.

    Only Chromium windows are considered.  Matching an arbitrary window by
    title would let "minimize to tray" terminate a regular browser instance
    (with the user's other tabs) when the default-browser fallback was used.
    """
    for hwnd, _pid, title, kind in _visible_windows():
        if kind == "Chrome_WidgetWin_1" and "AutoScrcpy" in title:
            return hwnd
    return 0


def find_scrcpy_window(pid: int, timeout: float = 8.0) -> int:
    """Wait for the scrcpy preview window owned by ``pid``."""
    if not IS_WINDOWS or not pid:
        return 0
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        for hwnd, window_pid, _title, _kind in _visible_windows():
            if window_pid == pid:
                return hwnd
        if time.monotonic() >= deadline:
            return 0
        time.sleep(0.12)


def find_window_for_process(pid: int) -> int:
    """Find a visible Chromium window owned by ``pid``.

    Chromium may not have updated the window title to the page title yet, so
    this is used as a fallback when reopening the console.
    """
    if not IS_WINDOWS or not pid:
        return 0
    for hwnd, window_pid, _title, kind in _visible_windows():
        if window_pid == pid and kind == "Chrome_WidgetWin_1":
            return hwnd
    return 0


def focus_window(hwnd: int) -> bool:
    """Bring ``hwnd`` to the foreground, working around the focus lock."""
    if not IS_WINDOWS or not hwnd or not _user32.IsWindow(hwnd):
        return False
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, SW_RESTORE)
    current_thread = int(_kernel32.GetCurrentThreadId())
    foreground = _user32.GetForegroundWindow()
    foreground_thread = (
        int(_user32.GetWindowThreadProcessId(foreground, None))
        if foreground
        else 0
    )
    target_thread = int(_user32.GetWindowThreadProcessId(hwnd, None))
    attached: list[int] = []
    try:
        for thread_id in {foreground_thread, target_thread}:
            if (
                thread_id
                and thread_id != current_thread
                and _user32.AttachThreadInput(current_thread, thread_id, True)
            ):
                attached.append(thread_id)
        _user32.BringWindowToTop(hwnd)
        _user32.SetForegroundWindow(hwnd)
        if _user32.GetForegroundWindow() != hwnd:
            # Windows may refuse the foreground request from a background
            # process (the window only flashes in the taskbar).  This older
            # API still switches to the window in that case.
            _user32.SwitchToThisWindow(hwnd, True)
        _user32.SetFocus(hwnd)
        return True
    except Exception:
        LOGGER.debug("Could not focus window %s", hwnd, exc_info=True)
        return False
    finally:
        for thread_id in attached:
            with contextlib.suppress(Exception):
                _user32.AttachThreadInput(current_thread, thread_id, False)


def is_minimized(hwnd: int) -> bool:
    if not IS_WINDOWS or not hwnd or not _user32.IsWindow(hwnd):
        return False
    return bool(_user32.IsIconic(hwnd))


def minimize_window(hwnd: int) -> bool:
    if not IS_WINDOWS or not hwnd or not _user32.IsWindow(hwnd):
        return False
    # Minimize without activating: the scrcpy window must keep the focus.
    return bool(_user32.ShowWindow(hwnd, SW_SHOWMINNOACTIVE))


def restore_window(hwnd: int) -> bool:
    if not IS_WINDOWS or not hwnd or not _user32.IsWindow(hwnd):
        return False
    _user32.ShowWindow(hwnd, SW_RESTORE)
    return focus_window(hwnd)


def _kill_process_tree(pid: int) -> None:
    if not pid or not IS_WINDOWS:
        return
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        LOGGER.debug("taskkill failed for pid %s", pid, exc_info=True)


def close_console_window(process: "subprocess.Popen[bytes] | None" = None) -> bool:
    """Close the chromeless browser so its memory is released.

    The tray keeps the Python backend alive; the browser is relaunched from the
    tray menu.  Closing the window first gives the page a chance to shut down
    cleanly, then the dedicated browser process tree is terminated.
    """
    if not IS_WINDOWS:
        return False
    hwnd = find_console_window()
    pid = window_process_id(hwnd) if hwnd else 0
    if not pid and process is not None and process.poll() is None:
        pid = process.pid
    if hwnd:
        with contextlib.suppress(Exception):
            _user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if not _user32.IsWindow(hwnd):
                break
            time.sleep(0.05)
    if pid:
        _kill_process_tree(pid)
    if process is not None and process.poll() is None:
        with contextlib.suppress(Exception):
            process.terminate()
        with contextlib.suppress(Exception):
            process.wait(timeout=3)
    return bool(hwnd or pid)


# -- Tray icon --------------------------------------------------------------


def system_uses_light_theme() -> bool:
    """Return whether the Windows taskbar currently uses the light theme."""
    if not IS_WINDOWS:
        return False
    try:
        import winreg

        path = (
            r"Software\Microsoft\Windows\CurrentVersion"
            r"\Themes\Personalize"
        )
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
        return bool(int(value))
    except Exception:
        return False


def tray_theme() -> str:
    """Return ``light`` or ``dark`` for the notification area."""
    return "light" if system_uses_light_theme() else "dark"


class TrayIcon:
    """A native notification-area icon with a small context menu."""

    def __init__(
        self,
        *,
        icon_path: Path,
        tooltip: str,
        on_open: Callable[[], None],
        on_quit: Callable[[], None],
        on_stop: Callable[[], None] | None = None,
        is_running: Callable[[], bool] | None = None,
        light_icon_path: Path | None = None,
    ) -> None:
        dark_path = Path(icon_path)
        self._icon_paths = {
            "dark": dark_path,
            "light": Path(light_icon_path) if light_icon_path else dark_path,
        }
        self._tooltip = tooltip[:127]
        self._on_open = on_open
        self._on_quit = on_quit
        self._on_stop = on_stop
        self._is_running = is_running
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._hwnd = 0
        self._hicon: int | None = None
        self._nid: NOTIFYICONDATAW | None = None
        self._wndproc: WNDPROC | None = None
        self._class_name = f"AutoScrcpyTray_{os.getpid()}_{id(self):x}"
        self._theme = tray_theme()
        self._taskbar_created = 0
        self._restore_attempts = 0
        self.available = False

    # -- lifecycle ---------------------------------------------------------

    def start(self, timeout: float = 2.5) -> bool:
        if not IS_WINDOWS or self._thread is not None:
            return self.available
        self._thread = threading.Thread(
            target=self._run, name="autoscrcpy-tray", daemon=True
        )
        self._thread.start()
        self._ready.wait(timeout)
        return self.available

    def stop(self) -> None:
        if not IS_WINDOWS:
            return
        thread = self._thread
        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            # ``start`` may have timed out while the icon was still being
            # created; give the tray thread a moment so the icon is cleaned up.
            self._ready.wait(3.0)
        hwnd = self._hwnd
        if hwnd:
            if self._nid is not None:
                with contextlib.suppress(Exception):
                    _shell32.Shell_NotifyIconW(
                        NIM_DELETE, ctypes.byref(self._nid)
                    )
                self._nid = None
            with contextlib.suppress(Exception):
                _user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self.available = False

    def notify(self, title: str, message: str) -> bool:
        """Show a tray balloon; safe to call from any thread."""
        if not IS_WINDOWS or not self.available or not self._hwnd:
            return False
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self._hwnd
        data.uID = 1
        data.uFlags = NIF_INFO
        data.szInfo = str(message)[:255]
        data.szInfoTitle = str(title)[:63]
        data.dwInfoFlags = NIIF_INFO
        return bool(_shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(data)))

    # -- internals ---------------------------------------------------------

    def _run(self) -> None:
        if not IS_WINDOWS:
            self._ready.set()
            return
        try:
            self._create()
            self.available = True
        except Exception as exc:
            if isinstance(exc, OSError):
                LOGGER.warning("Could not create the notification-area icon: %s", exc)
            else:
                LOGGER.exception("Could not create the notification-area icon")
            self.available = False
            self._teardown()
            return
        finally:
            self._ready.set()
        try:
            self._message_loop()
        except Exception:
            LOGGER.exception("Tray message loop stopped unexpectedly")
        finally:
            self.available = False
            self._teardown()

    def _create(self) -> None:
        hinstance = _kernel32.GetModuleHandleW(None)
        self._wndproc = WNDPROC(self._handle_message)
        window_class = WNDCLASSW()
        window_class.style = 0
        window_class.lpfnWndProc = self._wndproc
        window_class.hInstance = hinstance
        window_class.lpszClassName = self._class_name
        if not _user32.RegisterClassW(ctypes.byref(window_class)):
            error = ctypes.get_last_error()
            if error != ERROR_CLASS_ALREADY_EXISTS:
                raise OSError(error, "RegisterClassW failed")
        self._hwnd = _user32.CreateWindowExW(
            0,
            self._class_name,
            "AutoScrcpy",
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            hinstance,
            None,
        )
        if not self._hwnd:
            raise OSError(ctypes.get_last_error(), "CreateWindowExW failed")

        # The message is identical for every process; Explorer broadcasts it
        # after it restarts, and the notification-area icon must be re-added.
        self._taskbar_created = int(
            _user32.RegisterWindowMessageW("TaskbarCreated") or 0
        )

        added = False
        # Explorer may not have created its notification area yet when the app
        # is started at logon; retry briefly before giving up.
        for _ in range(4):
            if self._add_icon():
                added = True
                break
            time.sleep(0.25)
        if not added:
            raise OSError(ctypes.get_last_error(), "Shell_NotifyIconW failed")
        LOGGER.info(
            "Notification-area icon ready (%s theme)", self._theme
        )

    def _icon_data(self) -> tuple[NOTIFYICONDATAW, int] | None:
        """Build the notification data for the current theme."""
        if not self._hwnd:
            return None
        icon = self._load_icon()
        if not icon:
            return None
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self._hwnd
        data.uID = 1
        data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.uCallbackMessage = WM_TRAY
        data.hIcon = icon
        data.szTip = self._tooltip
        return data, int(icon)

    def _register_icon(self, flag: int = NIM_ADD) -> bool:
        """Add (or update) the notification-area icon."""
        prepared = self._icon_data()
        if prepared is None:
            return False
        data, icon = prepared
        if not _shell32.Shell_NotifyIconW(flag, ctypes.byref(data)):
            with contextlib.suppress(Exception):
                _user32.DestroyIcon(icon)
            return False
        previous = self._hicon
        self._hicon = icon
        self._nid = data
        if previous and previous != icon:
            with contextlib.suppress(Exception):
                _user32.DestroyIcon(previous)
        return True

    def _add_icon(self) -> bool:
        return self._register_icon(NIM_ADD)

    def _restore_taskbar_icon(self) -> None:
        """Re-add the icon after Explorer recreated the taskbar.

        ``NIM_ADD`` is the normal path.  If the shell still remembers the
        icon (``NIM_ADD`` fails with ``E_FAIL``), ``NIM_MODIFY`` refreshes it
        instead.  Until the new notification area accepts registrations both
        calls fail, so a timer retries without blocking the message loop.
        """
        if not IS_WINDOWS or not self._hwnd:
            return
        self._theme = tray_theme()
        if self._register_icon(NIM_ADD) or self._register_icon(NIM_MODIFY):
            self._restore_attempts = 0
            self._kill_restore_timer()
            LOGGER.info(
                "Notification-area icon restored after an Explorer restart"
            )
            return
        self._restore_attempts += 1
        if self._restore_attempts >= TASKBAR_RESTORE_MAX_ATTEMPTS:
            self._restore_attempts = 0
            self._kill_restore_timer()
            LOGGER.warning(
                "Could not restore the notification-area icon after "
                "Explorer restarted"
            )
            return
        if not _user32.SetTimer(
            self._hwnd,
            TASKBAR_RESTORE_TIMER,
            TASKBAR_RESTORE_INTERVAL_MS,
            None,
        ):
            LOGGER.warning("SetTimer failed while restoring the tray icon")

    def _kill_restore_timer(self) -> None:
        if self._hwnd:
            with contextlib.suppress(Exception):
                _user32.KillTimer(self._hwnd, TASKBAR_RESTORE_TIMER)

    def _icon_for_theme(self, theme: str | None = None) -> Path:
        key = theme or self._theme or tray_theme()
        path = self._icon_paths.get(key)
        if path is not None and path.is_file():
            return path
        return self._icon_paths["dark"]

    def _load_icon(self) -> int:
        size_x = _user32.GetSystemMetrics(SM_CXSMICON) or 16
        size_y = _user32.GetSystemMetrics(SM_CYSMICON) or 16
        icon = _user32.LoadImageW(
            None,
            str(self._icon_for_theme()),
            IMAGE_ICON,
            size_x,
            size_y,
            LR_LOADFROMFILE,
        )
        if not icon:
            icon = _user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
        return int(icon) if icon else 0

    def _refresh_icon(self) -> bool:
        """Reload the tray bitmap for the current Windows light/dark theme."""
        if not IS_WINDOWS or self._hwnd == 0:
            return False
        theme = tray_theme()
        self._theme = theme
        icon = self._load_icon()
        if not icon:
            return False
        if self._nid is None:
            return False
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self._hwnd
        data.uID = 1
        data.uFlags = NIF_ICON
        data.hIcon = icon
        updated = bool(
            _shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(data))
        )
        if not updated:
            with contextlib.suppress(Exception):
                _user32.DestroyIcon(icon)
            return False
        previous = self._hicon
        self._hicon = icon
        self._nid.hIcon = icon
        if previous:
            with contextlib.suppress(Exception):
                _user32.DestroyIcon(previous)
        LOGGER.info("Tray icon switched to the %s theme", theme)
        return True

    def _message_loop(self) -> None:
        message = MSG()
        while True:
            result = _user32.GetMessageW(ctypes.byref(message), None, 0, 0)
            if result == 0:
                return
            if result == -1:
                raise OSError(ctypes.get_last_error(), "GetMessageW failed")
            _user32.TranslateMessage(ctypes.byref(message))
            _user32.DispatchMessageW(ctypes.byref(message))

    def _teardown(self) -> None:
        if not IS_WINDOWS:
            return
        self._kill_restore_timer()
        if self._nid is not None:
            with contextlib.suppress(Exception):
                _shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            self._nid = None
        if self._hicon:
            with contextlib.suppress(Exception):
                _user32.DestroyIcon(self._hicon)
            self._hicon = None
        hwnd = self._hwnd
        self._hwnd = 0
        if hwnd and _user32.IsWindow(hwnd):
            with contextlib.suppress(Exception):
                _user32.DestroyWindow(hwnd)
        with contextlib.suppress(Exception):
            _user32.UnregisterClassW(
                self._class_name, _kernel32.GetModuleHandleW(None)
            )
        self._wndproc = None

    def _handle_message(
        self, hwnd: int, message: int, wparam: int, lparam: int
    ) -> int:
        if message == WM_TRAY:
            event = int(lparam) & 0xFFFF
            if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self._invoke(self._on_open)
            elif event == WM_RBUTTONUP:
                self._show_menu()
            return 0
        if self._taskbar_created and message == self._taskbar_created:
            # Explorer was restarted: the shell forgot every notification icon.
            self._restore_taskbar_icon()
            return 0
        if message == WM_TIMER and wparam == TASKBAR_RESTORE_TIMER:
            self._restore_taskbar_icon()
            return 0
        if message in (WM_SETTINGCHANGE, WM_THEMECHANGED):
            # Windows switched between light and dark taskbar; swap the
            # monochrome bitmap without recreating the tray icon.
            self._refresh_icon()
            return 0
        if message == WM_DPICHANGED:
            # SM_CXSMICON may have changed; reload the matching ICO size.
            self._refresh_icon()
            return 0
        if message == WM_CLOSE:
            _user32.DestroyWindow(hwnd)
            return 0
        if message == WM_DESTROY:
            _user32.PostQuitMessage(0)
            return 0
        return int(_user32.DefWindowProcW(hwnd, message, wparam, lparam) or 0)

    def _show_menu(self) -> None:
        menu = _user32.CreatePopupMenu()
        if not menu:
            return
        running = bool(self._is_running and self._is_running())
        _user32.AppendMenuW(menu, MF_STRING, MENU_OPEN, "打开控制台")
        _user32.AppendMenuW(
            menu,
            MF_STRING if running else MF_STRING | MF_GRAYED,
            MENU_STOP,
            "停止投屏",
        )
        _user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        _user32.AppendMenuW(menu, MF_STRING, MENU_QUIT, "退出 AutoScrcpy")

        point = wintypes.POINT()
        _user32.GetCursorPos(ctypes.byref(point))
        _user32.SetForegroundWindow(self._hwnd)
        command = _user32.TrackPopupMenu(
            menu,
            TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
            point.x,
            point.y,
            0,
            self._hwnd,
            None,
        )
        _user32.PostMessageW(self._hwnd, WM_NULL, 0, 0)
        _user32.DestroyMenu(menu)

        if command == MENU_OPEN:
            self._invoke(self._on_open)
        elif command == MENU_STOP and self._on_stop is not None:
            self._invoke(self._on_stop)
        elif command == MENU_QUIT:
            self._invoke(self._on_quit)

    def _invoke(self, callback: Callable[[], None] | None) -> None:
        if callback is None:
            return
        try:
            callback()
        except Exception:
            LOGGER.exception("Tray action failed")
