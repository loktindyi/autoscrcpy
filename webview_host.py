"""Native WebView2 window for AutoScrcpy (optional, Windows only).

The browser app window opened by :mod:`app` is a separate Edge/Chrome
process.  Windows 11 may restore that process after a reboot, which leaves an
empty window behind because the backend is not running yet.  It also means the
window's close button cannot be intercepted by the backend.

This module hosts the exact same local UI inside the AutoScrcpy process using
the Microsoft Edge WebView2 runtime (shipped with Windows 10/11).  It uses only
ctypes: no .NET, no pywebview, no extra Python dependency.  When the runtime or
the bundled ``WebView2Loader.dll`` is unavailable, :func:`webview_available`
reports why and the caller falls back to the browser window.

Threading model: the window and the WebView2 COM object live on their own STA
thread with a Win32 message loop.  The asyncio backend talks to it through a
small action queue + ``PostMessage``.  COM calls are deliberately executed
*after* the window procedure returns (between message dispatches) because
calling back into CPython from inside a ctypes WNDPROC callback is fragile.
"""

from __future__ import annotations

import contextlib
import ctypes
import ctypes.wintypes as w
import logging
import os
import platform
import struct
import threading
import time
from pathlib import Path
from typing import Callable

LOGGER = logging.getLogger("autoscrcpy")

IS_WINDOWS = os.name == "nt"
BASE_DIR = Path(__file__).resolve().parent
LOADER_DIR = BASE_DIR / "assets" / "webview2"

HRESULT = ctypes.c_long
ULONG = ctypes.c_ulong
LPVOID = ctypes.c_void_p

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_ERASEBKGND = 0x0014
WM_SETICON = 0x0080
WM_SIZE = 0x0005
WM_DPICHANGED = 0x02E0
WM_APP = 0x8000
WM_APP_ACTION = WM_APP + 17
WM_GETMINMAXINFO = 0x0024

SW_HIDE = 0
SW_SHOW = 5
SW_MINIMIZE = 6
SW_RESTORE = 9
SW_SHOWNORMAL = 1

ICON_SMALL = 0
ICON_BIG = 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040

WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_VISIBLE = 0x10000000
WS_EX_TOOLWINDOW = 0x00000080

MONITOR_DEFAULTTONEAREST = 2
SPI_GETWORKAREA = 0x0030

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36

MIN_WIDTH = 900
MIN_HEIGHT = 600


class WebViewUnavailable(RuntimeError):
    """Raised when the WebView2 runtime cannot be used."""


def _arch_suffix() -> str:
    if platform.machine().lower() in {"arm64", "aarch64"}:
        return "arm64"
    return "x64" if struct.calcsize("P") * 8 >= 64 else "x86"


def loader_path() -> Path | None:
    """Return the bundled loader DLL matching this Python interpreter."""
    preferred = LOADER_DIR / f"WebView2Loader-{_arch_suffix()}.dll"
    if preferred.is_file():
        return preferred
    for name in ("WebView2Loader-x64.dll", "WebView2Loader-x86.dll", "WebView2Loader-arm64.dll"):
        candidate = LOADER_DIR / name
        if candidate.is_file():
            return candidate
    return None


def runtime_version() -> str | None:
    """Best-effort detection of an installed Edge WebView2 runtime."""
    roots: list[Path] = []
    for variable, fallback in (
        ("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        ("PROGRAMFILES", r"C:\Program Files"),
    ):
        root = os.environ.get(variable) or fallback
        roots.append(Path(root) / "Microsoft" / "EdgeWebView" / "Application")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(Path(local) / "Microsoft" / "EdgeWebView" / "Application")
    best: tuple[tuple[int, ...], str] | None = None
    for root in roots:
        with contextlib.suppress(OSError):
            for entry in root.iterdir():
                if not entry.is_dir():
                    continue
                exe = entry / "msedgewebview2.exe"
                if not exe.is_file():
                    continue
                try:
                    parts = tuple(int(piece) for piece in entry.name.split(".")[:4])
                except ValueError:
                    parts = (0,)
                if best is None or parts > best[0]:
                    best = (parts, entry.name)
    return best[1] if best else None


def webview_available() -> tuple[bool, str]:
    """Return ``(available, reason)`` without creating any window."""
    if not IS_WINDOWS:
        return False, "WebView2 仅支持 Windows"
    if loader_path() is None:
        return False, "缺少 assets/webview2/WebView2Loader-*.dll"
    version = runtime_version()
    if version is None:
        return False, "未安装 Microsoft Edge WebView2 运行时"
    return True, f"WebView2 {version}"


# ---------------------------------------------------------------------------
# COM plumbing
# ---------------------------------------------------------------------------


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", w.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", w.HINSTANCE),
        ("hIcon", w.HICON),
        ("hCursor", w.HANDLE),
        ("hbrBackground", w.HANDLE),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
    ]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved", POINT),
        ("ptMaxSize", POINT),
        ("ptMaxPosition", POINT),
        ("ptMinTrackSize", POINT),
        ("ptMaxTrackSize", POINT),
    ]


class Interface(ctypes.Structure):
    _fields_ = [("vtable", ctypes.POINTER(LPVOID))]


class COREWEBVIEW2_COLOR(ctypes.Structure):
    _fields_ = [
        ("A", ctypes.c_ubyte),
        ("R", ctypes.c_ubyte),
        ("G", ctypes.c_ubyte),
        ("B", ctypes.c_ubyte),
    ]


def _call(ptr: int, index: int, restype, *argtypes):
    """Build a typed callable for a COM vtable slot."""
    table = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(LPVOID)))[0]
    return ctypes.cast(
        table[index], ctypes.WINFUNCTYPE(restype, LPVOID, *argtypes)
    )


def _add_ref(ptr: int) -> int:
    if not ptr:
        return 0
    return int(_call(ptr, 1, ULONG)(ptr) or 0)


def _release(ptr: int) -> int:
    if not ptr:
        return 0
    return int(_call(ptr, 2, ULONG)(ptr) or 0)


class _ComObject:
    """A tiny COM object exposing ``QueryInterface``/``AddRef``/``Release``."""

    def __init__(self, methods: list[tuple[Callable[..., int], tuple]]) -> None:
        self._refs = 1
        self._callbacks: list[ctypes._CFuncPtr] = []
        self._vtable = (LPVOID * max(16, len(methods) + 3))()
        self._interface = Interface()
        self._interface.vtable = ctypes.cast(
            ctypes.byref(self._vtable), ctypes.POINTER(LPVOID)
        )
        entries = [
            (self._query, (LPVOID, LPVOID)),
            (self._addref, ()),
            (self._release_self, ()),
            *methods,
        ]
        for index, (impl, argtypes) in enumerate(entries):
            callback = ctypes.WINFUNCTYPE(HRESULT, LPVOID, *argtypes)(impl)
            self._callbacks.append(callback)
            self._vtable[index] = ctypes.cast(callback, LPVOID)

    @property
    def pointer(self) -> LPVOID:
        return ctypes.cast(ctypes.byref(self._interface), LPVOID)

    def _query(self, this, riid, ppv):
        if not ppv:
            return -2147024809  # E_INVALIDARG
        ctypes.cast(ppv, ctypes.POINTER(LPVOID))[0] = self.pointer
        self._refs += 1
        return 0

    def _addref(self, this):
        self._refs += 1
        return self._refs

    def _release_self(self, this):
        self._refs -= 1
        return max(0, self._refs)


class _EnvironmentHandler(_ComObject):
    def __init__(self, host: "WebViewHost") -> None:
        self.host = host
        super().__init__([(self._invoke, (HRESULT, LPVOID))])

    def _invoke(self, this, result, environment):
        self.host._on_environment(result, environment)
        return 0


class _ControllerHandler(_ComObject):
    def __init__(self, host: "WebViewHost") -> None:
        self.host = host
        super().__init__([(self._invoke, (HRESULT, LPVOID))])

    def _invoke(self, this, result, controller):
        self.host._on_controller(result, controller)
        return 0


# ---------------------------------------------------------------------------
# The host
# ---------------------------------------------------------------------------


class WebViewHost:
    """A Win32 window that hosts the AutoScrcpy UI through WebView2."""

    def __init__(
        self,
        url: str,
        *,
        title: str,
        icon_path: Path | None,
        user_data_dir: Path,
        on_close: Callable[[], None] | None = None,
        appearance: str = "dark",
        width: int | None = None,
        height: int | None = None,
    ) -> None:
        self.url = url
        self.title = title
        self.icon_path = Path(icon_path) if icon_path else None
        self.user_data_dir = Path(user_data_dir)
        self._on_close = on_close
        self._appearance = "light" if appearance == "light" else "dark"
        self._width = width
        self._height = height

        self._hwnd = 0
        self._thread: threading.Thread | None = None
        self._created = threading.Event()
        self._done = threading.Event()
        self._actions: list[str] = []
        self._action_lock = threading.Lock()
        self._close_notified = False
        self._closing = False
        self._available = False
        self._error = ""

        self._controller = 0
        self._webview = 0
        self._put_bounds = None
        self._put_visible = None
        self._close_controller = None
        self._navigate = None
        self._wndproc = None
        self._class_name = f"AutoScrcpyWebView_{os.getpid()}_{id(self):x}"
        self._keep_refs: list[object] = []

        self._user32 = None
        self._kernel32 = None
        self._gdi32 = None
        self._dwmapi = None
        self._ole32 = None
        self._loader = None
        self._background_brush = 0

    # -- public API --------------------------------------------------------

    @property
    def available(self) -> bool:
        return self._available

    @property
    def running(self) -> bool:
        return bool(
            self._available
            and self._thread is not None
            and self._thread.is_alive()
            and not self._closing
        )

    @property
    def error(self) -> str:
        return self._error

    @property
    def minimized(self) -> bool:
        hwnd = self._hwnd
        if not hwnd or self._user32 is None:
            return False
        with contextlib.suppress(Exception):
            return bool(self._user32.IsIconic(hwnd))
        return False

    @property
    def visible(self) -> bool:
        hwnd = self._hwnd
        if not hwnd or self._user32 is None:
            return False
        with contextlib.suppress(Exception):
            return bool(self._user32.IsWindowVisible(hwnd))
        return False

    def start(self, timeout: float = 25.0) -> bool:
        """Create the window and block until WebView2 is ready."""
        if not IS_WINDOWS:
            self._error = "WebView2 仅支持 Windows"
            return False
        if self._thread is not None:
            return self._available
        self._thread = threading.Thread(
            target=self._thread_main, name="autoscrcpy-webview", daemon=True
        )
        self._thread.start()
        if not self._created.wait(max(1.0, timeout)):
            self._error = self._error or "创建 WebView2 窗口超时"
            LOGGER.warning("WebView2 window did not become ready: %s", self._error)
            self.stop(timeout=3.0)
            return False
        return self._available

    def stop(self, timeout: float = 5.0) -> None:
        """Close the window and wait for the UI thread to exit."""
        self._closing = True
        if self._thread is None:
            return
        self._post("quit")
        deadline = time.monotonic() + max(0.5, timeout)
        while not self._done.is_set() and time.monotonic() < deadline:
            time.sleep(0.03)
            if self._hwnd:
                # The window procedure may have consumed the first message
                # before the loop started pumping; keep asking until it exits.
                self._post("quit")
        thread = self._thread
        if thread is not None and thread.is_alive():
            LOGGER.warning("WebView2 window thread did not exit in time")
            with contextlib.suppress(Exception):
                if self._hwnd:
                    self._user32.PostMessageW(self._hwnd, WM_APP_ACTION, 0, 0)
        self._available = False

    def set_appearance(self, value: str) -> None:
        """Switch the native title bar between light and dark."""
        appearance = "light" if value == "light" else "dark"
        if appearance == self._appearance:
            return
        self._appearance = appearance
        self._post("look")

    def show_restore(self) -> None:
        self._post("show")

    def hide(self) -> None:
        self._post("hide")

    def minimize(self) -> None:
        self._post("minimize")

    def focus(self) -> None:
        self._post("focus")

    # -- thread plumbing ---------------------------------------------------

    def _post(self, action: str) -> None:
        with self._action_lock:
            if action == "layout" and "layout" in self._actions:
                return
            if action == "quit" and "quit" in self._actions:
                return
            self._actions.append(action)
        hwnd = self._hwnd
        if hwnd and self._user32 is not None:
            with contextlib.suppress(Exception):
                self._user32.PostMessageW(hwnd, WM_APP_ACTION, 0, 0)

    def _drain(self) -> list[str]:
        with self._action_lock:
            actions = self._actions
            self._actions = []
        return actions

    def _notify_close(self) -> None:
        if self._close_notified:
            return
        self._close_notified = True
        callback = self._on_close
        if callback is not None:
            try:
                callback()
            except Exception:
                LOGGER.exception("WebView2 close callback failed")

    # -- window thread -----------------------------------------------------

    def _thread_main(self) -> None:
        try:
            self._user32 = ctypes.WinDLL("user32", use_last_error=True)
            self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self._gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
            self._ole32 = ctypes.WinDLL("ole32", use_last_error=True)
            with contextlib.suppress(Exception):
                self._dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
            self._bind_functions()
            if self._ole32.CoInitializeEx(None, 2) < 0:
                raise WebViewUnavailable("COM 初始化失败")
            try:
                self._create_window()
                self._create_environment()
                self._message_loop()
            finally:
                self._shutdown_com()
                with contextlib.suppress(Exception):
                    self._ole32.CoUninitialize()
        except Exception as exc:
            self._error = str(exc) or exc.__class__.__name__
            LOGGER.warning("WebView2 window unavailable: %s", exc)
            if isinstance(exc, OSError):
                LOGGER.debug("WebView2 startup failure", exc_info=True)
            with contextlib.suppress(Exception):
                if self._hwnd and self._user32 is not None:
                    self._user32.DestroyWindow(self._hwnd)
        finally:
            self._available = False
            self._created.set()
            self._done.set()

    def _bind_functions(self) -> None:
        u = self._user32
        assert u is not None
        u.CreateWindowExW.argtypes = [
            w.DWORD, ctypes.c_wchar_p, ctypes.c_wchar_p, w.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            w.HWND, w.HANDLE, w.HINSTANCE, LPVOID,
        ]
        u.CreateWindowExW.restype = w.HWND
        u.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, ctypes.c_ssize_t]
        u.DefWindowProcW.restype = ctypes.c_ssize_t
        u.DestroyWindow.argtypes = [w.HWND]
        u.DestroyWindow.restype = w.BOOL
        u.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
        u.ShowWindow.restype = w.BOOL
        u.SetForegroundWindow.argtypes = [w.HWND]
        u.SetForegroundWindow.restype = w.BOOL
        u.SetWindowTextW.argtypes = [w.HWND, ctypes.c_wchar_p]
        u.GetClientRect.argtypes = [w.HWND, ctypes.POINTER(RECT)]
        u.SystemParametersInfoW.argtypes = [w.UINT, w.UINT, LPVOID, w.UINT]
        u.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
        u.GetMessageW.restype = ctypes.c_int
        u.TranslateMessage.argtypes = [ctypes.POINTER(w.MSG)]
        u.DispatchMessageW.argtypes = [ctypes.POINTER(w.MSG)]
        u.DispatchMessageW.restype = ctypes.c_ssize_t
        u.PostQuitMessage.argtypes = [ctypes.c_int]
        u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, ctypes.c_ssize_t]
        u.PostMessageW.restype = w.BOOL
        u.LoadImageW.argtypes = [w.HINSTANCE, ctypes.c_wchar_p, w.UINT, ctypes.c_int, ctypes.c_int, w.UINT]
        u.LoadImageW.restype = w.HANDLE
        u.SendMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, ctypes.c_ssize_t]
        u.SendMessageW.restype = ctypes.c_ssize_t
        u.SetTimer.argtypes = [w.HWND, w.UINT, w.UINT, LPVOID]
        u.SetTimer.restype = w.UINT
        u.KillTimer.argtypes = [w.HWND, w.UINT]
        u.KillTimer.restype = w.BOOL
        u.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        u.RegisterClassW.restype = w.WORD
        u.UnregisterClassW.argtypes = [ctypes.c_wchar_p, w.HINSTANCE]
        u.UnregisterClassW.restype = w.BOOL
        u.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.UINT]
        u.SetWindowPos.restype = w.BOOL
        u.IsIconic.argtypes = [w.HWND]
        u.IsIconic.restype = w.BOOL
        u.FillRect.argtypes = [w.HDC, ctypes.POINTER(RECT), w.HANDLE]
        u.FillRect.restype = ctypes.c_int
        k = self._kernel32
        assert k is not None
        k.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        k.GetModuleHandleW.restype = w.HINSTANCE
        g = self._gdi32
        assert g is not None
        g.DeleteObject.argtypes = [w.HANDLE]
        g.DeleteObject.restype = w.BOOL
        g.CreateSolidBrush.argtypes = [w.DWORD]
        g.CreateSolidBrush.restype = w.HANDLE
        if self._dwmapi is not None:
            self._dwmapi.DwmSetWindowAttribute.argtypes = [
                w.HWND, w.DWORD, LPVOID, w.DWORD
            ]
            self._dwmapi.DwmSetWindowAttribute.restype = HRESULT

    def _create_window(self) -> None:
        u = self._user32
        assert u is not None and self._kernel32 is not None
        hinstance = self._kernel32.GetModuleHandleW(None)
        rect = RECT()
        with contextlib.suppress(Exception):
            u.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
        work_w = max(MIN_WIDTH + 80, rect.right - rect.left) if rect.right else 1920
        work_h = max(MIN_HEIGHT + 80, rect.bottom - rect.top) if rect.bottom else 1080
        width = self._width or max(980, min(1480, work_w - 80))
        height = self._height or max(680, min(940, work_h - 80))
        width = max(MIN_WIDTH, min(width, work_w))
        height = max(MIN_HEIGHT, min(height, work_h))
        left = rect.left + max(0, (work_w - width) // 2)
        top = rect.top + max(0, (work_h - height) // 2)

        self._wndproc = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, w.HWND, w.UINT, w.WPARAM, ctypes.c_ssize_t
        )(self._handle_message)
        self._keep_refs.append(self._wndproc)
        if self._gdi32 is not None:
            self._background_brush = self._gdi32.CreateSolidBrush(0x00100A08)
        window_class = WNDCLASSW()
        window_class.lpfnWndProc = ctypes.cast(self._wndproc, LPVOID)
        window_class.hInstance = hinstance
        window_class.lpszClassName = self._class_name
        window_class.hbrBackground = self._background_brush
        if not u.RegisterClassW(ctypes.byref(window_class)):
            error = ctypes.get_last_error()
            if error != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                raise ctypes.WinError(error)
        self._hwnd = u.CreateWindowExW(
            0,
            self._class_name,
            self.title,
            WS_OVERLAPPEDWINDOW | WS_VISIBLE,
            left,
            top,
            width,
            height,
            None,
            None,
            hinstance,
            None,
        )
        if not self._hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        LOGGER.info("WebView2 window created (%sx%s)", width, height)
        self._apply_window_look()

    def _apply_window_look(self) -> None:
        u = self._user32
        assert u is not None
        icon = None
        if self.icon_path is not None and self.icon_path.is_file():
            with contextlib.suppress(Exception):
                icon = u.LoadImageW(
                    None, str(self.icon_path), IMAGE_ICON, 0, 0,
                    LR_LOADFROMFILE | LR_DEFAULTSIZE,
                )
        if icon:
            u.SendMessageW(self._hwnd, WM_SETICON, ICON_SMALL, icon)
            u.SendMessageW(self._hwnd, WM_SETICON, ICON_BIG, icon)
        if self._dwmapi is not None:
            light = self._appearance == "light"
            dark = ctypes.c_int(0 if light else 1)
            with contextlib.suppress(Exception):
                self._dwmapi.DwmSetWindowAttribute(
                    self._hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                    ctypes.byref(dark), ctypes.sizeof(dark),
                )
            caption = ctypes.c_uint(0x00F7F4F2 if light else 0x000F0B08)
            with contextlib.suppress(Exception):
                self._dwmapi.DwmSetWindowAttribute(
                    self._hwnd, DWMWA_CAPTION_COLOR,
                    ctypes.byref(caption), ctypes.sizeof(caption),
                )
            text = ctypes.c_uint(0x00261C16 if light else 0x00F3F1EE)
            with contextlib.suppress(Exception):
                self._dwmapi.DwmSetWindowAttribute(
                    self._hwnd, DWMWA_TEXT_COLOR,
                    ctypes.byref(text), ctypes.sizeof(text),
                )

    def _create_environment(self) -> None:
        path = loader_path()
        if path is None:
            raise WebViewUnavailable("缺少 WebView2Loader.dll")
        self._loader = ctypes.WinDLL(str(path))
        create_environment = self._loader.CreateCoreWebView2EnvironmentWithOptions
        create_environment.argtypes = [
            ctypes.c_wchar_p, ctypes.c_wchar_p, LPVOID, LPVOID
        ]
        create_environment.restype = HRESULT
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        handler = _EnvironmentHandler(self)
        self._keep_refs.append(handler)
        result = create_environment(
            None, str(self.user_data_dir), None, handler.pointer
        )
        if result < 0:
            raise WebViewUnavailable(f"WebView2 环境创建失败（0x{result & 0xFFFFFFFF:08X}）")

    def _on_environment(self, result: int, environment: int) -> None:
        if result < 0 or not environment:
            self._error = f"WebView2 环境创建失败（0x{result & 0xFFFFFFFF:08X}）"
            self._created.set()
            self._post("quit")
            return
        handler = _ControllerHandler(self)
        self._keep_refs.append(handler)
        create_controller = _call(environment, 3, HRESULT, w.HWND, LPVOID)
        code = create_controller(environment, w.HWND(self._hwnd), handler.pointer)
        if code < 0:
            self._error = f"WebView2 控制器创建失败（0x{code & 0xFFFFFFFF:08X}）"
            self._created.set()
            self._post("quit")

    def _on_controller(self, result: int, controller: int) -> None:
        if result < 0 or not controller:
            self._error = f"WebView2 控制器创建失败（0x{result & 0xFFFFFFFF:08X}）"
            self._created.set()
            self._post("quit")
            return
        _add_ref(controller)
        self._controller = int(controller)
        self._put_bounds = _call(controller, 6, HRESULT, RECT)
        self._put_visible = _call(controller, 4, HRESULT, w.BOOL)
        self._close_controller = _call(controller, 24, HRESULT)
        out = LPVOID()
        get_webview = _call(controller, 25, HRESULT, ctypes.POINTER(LPVOID))
        code = get_webview(controller, ctypes.byref(out))
        if code >= 0 and out.value:
            _add_ref(out.value)
            self._webview = int(out.value)
            self._navigate = _call(self._webview, 5, HRESULT, ctypes.c_wchar_p)
        self._available = True
        self._post("activate")
        self._created.set()

    def _activate(self) -> None:
        """Initial layout, dark background, settings and navigation."""
        controller = self._controller
        if not controller:
            return
        if self._put_visible is not None:
            with contextlib.suppress(Exception):
                self._put_visible(controller, True)
        with contextlib.suppress(Exception):
            put_background = _call(controller, 27, HRESULT, COREWEBVIEW2_COLOR)
            put_background(controller, COREWEBVIEW2_COLOR(255, 8, 10, 14))
        self._update_bounds()
        if self._webview:
            self._configure_webview()
            if self._navigate is not None:
                code = self._navigate(self._webview, self.url)
                LOGGER.info("WebView2 navigate %s -> 0x%08X", self.url, code & 0xFFFFFFFF)

    def _configure_webview(self) -> None:
        webview = self._webview
        if not webview:
            return
        try:
            settings = LPVOID()
            get_settings = _call(webview, 3, HRESULT, ctypes.POINTER(LPVOID))
            code = get_settings(webview, ctypes.byref(settings))
            if code < 0 or not settings.value:
                return
            value = settings.value
            try:
                for index, enabled in ((10, False), (12, False), (16, False)):
                    with contextlib.suppress(Exception):
                        _call(value, index, HRESULT, w.BOOL)(value, enabled)
            finally:
                _release(value)
        except Exception:
            LOGGER.debug("Could not change WebView2 settings", exc_info=True)

    def _update_bounds(self) -> None:
        if not self._controller or self._put_bounds is None:
            return
        rect = RECT()
        if not self._user32.GetClientRect(self._hwnd, ctypes.byref(rect)):
            return
        with contextlib.suppress(Exception):
            self._put_bounds(self._controller, rect)

    def _message_loop(self) -> None:
        message = w.MSG()
        while self._user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            self._user32.TranslateMessage(ctypes.byref(message))
            self._user32.DispatchMessageW(ctypes.byref(message))
            self._process_actions()

    def _process_actions(self) -> None:
        for action in self._drain():
            try:
                if action == "quit":
                    self._quit_window()
                elif action == "close-request":
                    # The backend decides whether this means "park in the
                    # tray" or "quit"; either way the front-end is stopped.
                    self._notify_close()
                elif action == "look":
                    self._apply_window_look()
                elif action == "show":
                    if self._user32.IsIconic(self._hwnd):
                        self._user32.ShowWindow(self._hwnd, SW_RESTORE)
                    else:
                        self._user32.ShowWindow(self._hwnd, SW_SHOW)
                    self._user32.SetForegroundWindow(self._hwnd)
                    self._update_bounds()
                elif action == "hide":
                    self._user32.ShowWindow(self._hwnd, SW_HIDE)
                elif action == "minimize":
                    self._user32.ShowWindow(self._hwnd, SW_MINIMIZE)
                elif action == "focus":
                    self._user32.SetForegroundWindow(self._hwnd)
                    self._update_bounds()
                elif action == "layout":
                    self._update_bounds()
                elif action == "activate":
                    self._activate()
            except Exception:
                LOGGER.exception("WebView2 host action failed: %s", action)
        if self._closing and not self._hwnd:
            return

    def _quit_window(self) -> None:
        if not self._hwnd:
            return
        self._available = False
        if self._controller and self._close_controller is not None:
            with contextlib.suppress(Exception):
                self._close_controller(self._controller)
            self._controller = 0
        self._user32.DestroyWindow(self._hwnd)
        self._hwnd = 0

    def _handle_message(self, hwnd, message, wparam, lparam):
        u = self._user32
        if message == WM_CLOSE:
            self._post("quit" if self._closing else "close-request")
            return 0
        if message == WM_SIZE:
            self._post("layout")
            return 0
        if message == WM_DPICHANGED:
            self._post("layout")
        if message == WM_GETMINMAXINFO and lparam:
            info = ctypes.cast(lparam, ctypes.POINTER(MINMAXINFO)).contents
            info.ptMinTrackSize.x = MIN_WIDTH
            info.ptMinTrackSize.y = MIN_HEIGHT
            return 0
        if message == WM_ERASEBKGND and wparam:
            rect = RECT()
            u.GetClientRect(hwnd, ctypes.byref(rect))
            with contextlib.suppress(Exception):
                u.FillRect(w.HDC(wparam), ctypes.byref(rect), self._background_brush)
            return 1
        if message == WM_DESTROY:
            u.PostQuitMessage(0)
            return 0
        return int(u.DefWindowProcW(hwnd, message, wparam, lparam) or 0)

    def _shutdown_com(self) -> None:
        if self._webview:
            with contextlib.suppress(Exception):
                _release(self._webview)
            self._webview = 0
        if self._controller:
            with contextlib.suppress(Exception):
                # The window is normally destroyed by _quit_window(); this is
                # the last-resort cleanup path (startup failure / hard close).
                if self._close_controller is not None:
                    self._close_controller(self._controller)
            self._controller = 0
        self._put_bounds = None
        self._put_visible = None
        self._close_controller = None
        self._navigate = None
        if self._hwnd:
            with contextlib.suppress(Exception):
                self._user32.DestroyWindow(self._hwnd)
            self._hwnd = 0
        if self._background_brush and self._gdi32 is not None:
            with contextlib.suppress(Exception):
                self._gdi32.DeleteObject(self._background_brush)
            self._background_brush = 0
        if self._kernel32 is not None and self._user32 is not None:
            with contextlib.suppress(Exception):
                self._user32.UnregisterClassW(
                    self._class_name, self._kernel32.GetModuleHandleW(None)
                )

