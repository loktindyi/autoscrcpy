#!/usr/bin/env python3
"""AutoScrcpy - a local, native-window UI for scrcpy.

The Python process is the backend.  It serves the editable files under ``ui/``
and the WebSocket endpoint on the same loopback-only port, then hosts the UI in
a native WebView2 window (``webview_host.py``).  When WebView2 is unavailable it
falls back to a chromeless Edge/Chrome app window.  There is deliberately no
framework or database: the front-end builds the scrcpy argv, the backend
executes it without a shell.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import ctypes
import json
import logging
import mimetypes
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import unquote, urlsplit

import websockets
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Headers, Request, Response

import webview_host
import win_tray

APP_NAME = "AutoScrcpy"
APP_VERSION = "2.3.0"
BASE_DIR = Path(__file__).resolve().parent
UI_DIR = BASE_DIR / "ui"
TRAY_ICON_PATH = BASE_DIR / "assets" / "autoscrcpy.ico"
TRAY_ICON_DARK_PATH = BASE_DIR / "assets" / "tray-dark.ico"
TRAY_ICON_LIGHT_PATH = BASE_DIR / "assets" / "tray-light.ico"
HOST = "127.0.0.1"
FIRST_CONNECT_TIMEOUT = 90.0
RECONNECT_GRACE = 3.0
CONSOLE_RESTORE_DELAY = 0.4
MAX_MESSAGE = 1_048_576
MAX_LOG_LINE = 8_000
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ACCENTS = {
    "teal": "青碧",
    "blue": "海蓝",
    "indigo": "靛蓝",
    "violet": "紫罗兰",
    "rose": "玫瑰",
    "amber": "琥珀",
    "lime": "青柠",
    "slate": "石墨",
}
APPEARANCES = {"light", "dark", "system"}
LEGACY_THEMES = {
    "midnight": "teal",
    "ember": "amber",
    "paper": "slate",
    "terminal": "lime",
}
AFTER_START_ACTIONS = {"focus", "minimize", "tray"}
WINDOW_BACKENDS = {"auto", "webview", "browser"}
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
OPTION_RE = re.compile(r"--[a-z0-9][a-z0-9-]*")
ADDRESS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]*(?::\d{1,5})?$")

LOGGER = logging.getLogger("autoscrcpy")

DEFAULT_SETTINGS: dict[str, Any] = {
    "version": 2,
    "updatedAt": 0,
    "accent": "teal",
    "appearance": "system",
    "uiScale": "system",
    "afterStart": "focus",
    "autoOpenConsole": True,
    "keepInBackground": True,
    "selectedDevice": "",
    "wirelessAddress": "",
    "collapsedSections": ["advanced", "record"],
    "options": {},
    "extraArgs": "",
    "profiles": [],
    "lastProfile": None,
}

SETTINGS_KEYS = {
    "version",
    "updatedAt",
    "accent",
    "appearance",
    "uiScale",
    "afterStart",
    "autoOpenConsole",
    "keepInBackground",
    "selectedDevice",
    "wirelessAddress",
    "collapsedSections",
    "options",
    "extraArgs",
    "profiles",
    "lastProfile",
}


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def decode_bytes(data: bytes | None) -> str:
    """Decode tool output.  scrcpy is UTF-8, older Windows tools may be GBK."""
    if not data:
        return ""
    for encoding in ("utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def process_creation_flags() -> int:
    return CREATE_NO_WINDOW if os.name == "nt" else 0


def show_native_error(title: str, message: str) -> None:
    """A hidden pythonw process has no console; use a message box on failure."""
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    except Exception:
        pass


def default_config_dir() -> Path:
    override = os.environ.get("AUTOSCRCPY_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if root:
            return Path(root) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def load_settings(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return json.loads(json_text(DEFAULT_SETTINGS))
    except (OSError, ValueError) as exc:
        LOGGER.warning("Could not read settings %s: %s", path, exc)
        return json.loads(json_text(DEFAULT_SETTINGS))
    return sanitize_settings(raw)


def sanitize_options(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    options: dict[str, Any] = {}
    for opt_key, opt_value in list(raw.items())[:300]:
        if not isinstance(opt_key, str) or len(opt_key) > 80:
            continue
        if isinstance(opt_value, bool):
            options[opt_key] = opt_value
        elif isinstance(opt_value, (int, float)) and not isinstance(opt_value, bool):
            options[opt_key] = opt_value
        elif isinstance(opt_value, str):
            options[opt_key] = opt_value[:4096]
        elif opt_value is None:
            options[opt_key] = None
    return options


def sanitize_profile(raw: Any, *, last: bool = False) -> dict[str, Any] | None:
    """Validate a named configuration snapshot stored with the draft settings."""
    if not isinstance(raw, dict):
        return None

    if last:
        if not any(raw.get(key) for key in ("updatedAt", "command", "options", "argv")):
            return None
        profile_id = "last"
        name = "上一次"
    else:
        profile_id = raw.get("id")
        name = raw.get("name")
        if (
            not isinstance(profile_id, str)
            or not profile_id
            or len(profile_id) > 100
            or not isinstance(name, str)
            or not name.strip()
        ):
            return None
        profile_id = profile_id[:100]
        name = name.strip()[:60]
        if name == "上一次":
            return None

    def timestamp(key: str) -> int:
        value = raw.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return max(0, min(int(value), 9_999_999_999_999))
        return 0

    argv = raw.get("argv")
    if not isinstance(argv, list):
        argv = []
    argv = [arg[:4096] for arg in argv[:200] if isinstance(arg, str)]

    return {
        "id": profile_id,
        "name": name,
        "createdAt": timestamp("createdAt"),
        "updatedAt": timestamp("updatedAt"),
        "selectedDevice": (
            raw["selectedDevice"][:300]
            if isinstance(raw.get("selectedDevice"), str)
            else ""
        ),
        "deviceLabel": (
            raw["deviceLabel"][:120] if isinstance(raw.get("deviceLabel"), str) else ""
        ),
        "command": (
            raw["command"][:16_000] if isinstance(raw.get("command"), str) else ""
        ),
        "optionCount": (
            max(0, min(int(raw["optionCount"]), 500))
            if isinstance(raw.get("optionCount"), (int, float))
            and not isinstance(raw.get("optionCount"), bool)
            else 0
        ),
        "options": sanitize_options(raw.get("options")),
        "argv": argv,
        "extraArgs": (
            raw["extraArgs"][:4000] if isinstance(raw.get("extraArgs"), str) else ""
        ),
    }


def sanitize_profiles(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    profiles: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in raw[:100]:
        profile = sanitize_profile(item)
        if profile is None or profile["id"] in seen_ids:
            continue
        seen_ids.add(profile["id"])
        profiles.append(profile)
    return profiles


def sanitize_settings(raw: Any) -> dict[str, Any]:
    """Keep the persisted file bounded and the front-end contract predictable."""
    result = json.loads(json_text(DEFAULT_SETTINGS))
    if not isinstance(raw, dict):
        return result

    for key in SETTINGS_KEYS & raw.keys():
        value = raw[key]
        if key == "accent":
            if isinstance(value, str) and value in ACCENTS:
                result["accent"] = value
        elif key == "appearance":
            if isinstance(value, str) and value in APPEARANCES:
                result["appearance"] = value
        elif key == "uiScale":
            if value == "system":
                result["uiScale"] = "system"
            elif isinstance(value, str) and value.isdigit():
                percent = int(value)
                if 70 <= percent <= 250:
                    result["uiScale"] = str(percent)
        elif key == "afterStart":
            if isinstance(value, str) and value in AFTER_START_ACTIONS:
                result["afterStart"] = value
        elif key == "autoOpenConsole":
            if isinstance(value, bool):
                result["autoOpenConsole"] = value
        elif key == "keepInBackground":
            if isinstance(value, bool):
                result["keepInBackground"] = value
        elif key == "updatedAt":
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                result["updatedAt"] = max(0, min(int(value), 9_999_999_999_999))
        elif key == "options":
            result["options"] = sanitize_options(value)
        elif key == "extraArgs":
            if isinstance(value, str):
                result["extraArgs"] = value[:4000]
        elif key == "profiles":
            result["profiles"] = sanitize_profiles(value)
        elif key == "lastProfile":
            result["lastProfile"] = sanitize_profile(value, last=True)
        elif key == "collapsedSections":
            if isinstance(value, list):
                collapsed: list[str] = []
                seen_sections: set[str] = set()
                for item in value[:30]:
                    if isinstance(item, str) and item and item not in seen_sections:
                        collapsed.append(item[:60])
                        seen_sections.add(item)
                result["collapsedSections"] = collapsed
        elif key in {"selectedDevice", "wirelessAddress"}:
            if isinstance(value, str):
                result[key] = value[:300]

    # 1.x stored four named themes; map them onto the new accent palette.
    legacy_theme = raw.get("theme")
    if "accent" not in raw and isinstance(legacy_theme, str):
        mapped = LEGACY_THEMES.get(legacy_theme)
        if mapped:
            result["accent"] = mapped
    return result


def save_settings_atomic(path: Path, settings: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(settings, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def load_window_state(path: Path) -> dict[str, Any] | None:
    """Read the remembered WebView2 window geometry, if it is still valid."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    result: dict[str, Any] = {}
    for key in ("x", "y", "width", "height"):
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        number = int(value)
        if key in {"width", "height"}:
            if not 400 <= number <= 20_000:
                return None
        elif not -100_000 <= number <= 100_000:
            return None
        result[key] = number
    result["maximized"] = bool(raw.get("maximized"))
    return result


def allocate_socket(port: int = 0) -> socket.socket:
    """Bind now so the port cannot be stolen before the server starts."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name == "nt":
        # Do not let another process bind this exact port beside us.
        with contextlib.suppress(OSError):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    sock.bind((HOST, port))
    sock.setblocking(False)
    return sock


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def screen_size() -> tuple[int, int]:
    if os.name != "nt":
        return (0, 0)
    try:
        user32 = ctypes.windll.user32
        return (int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1)))
    except Exception:
        return (0, 0)


def get_system_scale() -> float | None:
    """Return the Windows display scale (125% -> 1.25), if available."""
    if os.name != "nt":
        return None
    dpi = 0
    try:
        dpi = int(ctypes.windll.user32.GetDpiForSystem())
    except Exception:
        dpi = 0
    if not dpi:
        hdc = 0
        try:
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            hdc = int(user32.GetDC(None))
            if hdc:
                dpi = int(gdi32.GetDeviceCaps(hdc, 88))  # LOGPIXELSX
        except Exception:
            dpi = 0
        finally:
            if hdc:
                with contextlib.suppress(Exception):
                    ctypes.windll.user32.ReleaseDC(None, hdc)
    if dpi <= 0:
        return None
    return round(max(0.5, min(4.0, dpi / 96.0)), 4)


def system_appearance() -> str:
    """Return Windows' app theme: ``light`` or ``dark``."""
    if os.name != "nt":
        return "dark"
    try:
        import winreg

        path = (
            r"Software\Microsoft\Windows\CurrentVersion"
            r"\Themes\Personalize"
        )
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if int(value) else "dark"
    except Exception:
        return "dark"


def resolve_appearance(value: Any) -> str:
    """Resolve a stored ``appearance`` setting to ``light`` or ``dark``."""
    if value == "light":
        return "light"
    if value == "dark":
        return "dark"
    return system_appearance()


def find_browser() -> str | None:
    override = os.environ.get("AUTOSCRCPY_BROWSER")
    if override and Path(override).is_file():
        return override

    candidates = []
    if os.name == "nt":
        program_files = [
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("LOCALAPPDATA", ""),
        ]
        for root in program_files:
            if not root:
                continue
            candidates.extend(
                [
                    Path(root) / "Microsoft/Edge/Application/msedge.exe",
                    Path(root) / "Google/Chrome/Application/chrome.exe",
                ]
            )
    for name in ("msedge", "chrome", "chromium"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    for candidate in candidates:
        with contextlib.suppress(OSError):
            if candidate.is_file():
                return str(candidate)
    return None


def open_ui_window(
    url: str, profile_dir: Path, no_browser: bool
) -> tuple[str, subprocess.Popen[bytes] | None]:
    """Open a chromeless app window when Edge/Chrome exists."""
    if no_browser:
        return "disabled", None
    browser = find_browser()
    if not browser:
        opened = False
        with contextlib.suppress(Exception):
            opened = bool(webbrowser.open(url, new=1))
        return ("default-browser" if opened else "failed"), None

    # Chromium interprets --window-size in DIPs; this process is DPI aware, so
    # convert the physical target size back to DIPs to keep the window sane.
    scale = get_system_scale() or 1.0
    screen_w, screen_h = screen_size()
    width = clamp(screen_w - 80, 980, 1480) if screen_w else 1480
    height = clamp(screen_h - 110, 680, 940) if screen_h else 940
    width = max(640, int(width / scale))
    height = max(480, int(height / scale))
    with contextlib.suppress(OSError):
        profile_dir.mkdir(parents=True, exist_ok=True)
    args = [
        browser,
        f"--app={url}",
        f"--window-size={width},{height}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-mode",
        "--disable-session-crashed-bubble",
        "--hide-crash-restore-bubble",
    ]
    try:
        process = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            close_fds=True,
        )
        return browser, process
    except OSError as exc:
        LOGGER.warning("Could not start %s: %s", browser, exc)
        with contextlib.suppress(Exception):
            if webbrowser.open(url, new=1):
                return "default-browser", None
        return "failed", None


def _run_capture_blocking(
    argv: list[str], timeout: float, cwd: Path | None
) -> tuple[int, str]:
    """Use plain pipes instead of asyncio's Windows named-pipe transports.

    asyncio subprocesses require named pipes on Windows, which are unavailable
    in some restricted/sandboxed sessions.  subprocess.run works there and is
    simpler for short one-shot commands.
    """
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            creationflags=process_creation_flags(),
        )
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"命令超时（{timeout:.0f} 秒）") from None
    return completed.returncode or 0, decode_bytes(completed.stdout)


async def run_capture(
    argv: list[str], timeout: float = 20.0, cwd: Path | None = None
) -> tuple[int, str]:
    return await asyncio.to_thread(_run_capture_blocking, argv, timeout, cwd)


# ---------------------------------------------------------------------------
# Tool discovery and adb
# ---------------------------------------------------------------------------


def parse_supported_args(help_text: str) -> list[str]:
    """Extract long option names from the ``scrcpy --help`` output.

    Option lines are indented by exactly four spaces; wrapped descriptions are
    indented further, so they are ignored.
    """
    supported: set[str] = set()
    for line in help_text.splitlines():
        if line.startswith("    ") and not line.startswith("        "):
            supported.update(OPTION_RE.findall(line[:100]))
    return sorted(supported)


async def discover_tools() -> dict[str, Any]:
    scrcpy_path = shutil.which("scrcpy")
    adb_path = shutil.which("adb")
    if not adb_path and scrcpy_path:
        beside = Path(scrcpy_path).with_name("adb.exe")
        if beside.is_file():
            adb_path = str(beside)

    info: dict[str, Any] = {
        "scrcpyPath": scrcpy_path,
        "scrcpyVersion": None,
        "supportedArgs": [],
        "adbPath": adb_path,
        "adbVersion": None,
        "errors": [],
    }

    if scrcpy_path:
        try:
            code, output = await run_capture([scrcpy_path, "--version"], 12)
            first_line = next(
                (line.strip() for line in output.splitlines() if line.strip()), ""
            )
            match = re.search(r"scrcpy\s+([^\s<]+)", first_line, re.IGNORECASE)
            if match:
                info["scrcpyVersion"] = match.group(1)
            elif first_line:
                info["scrcpyVersion"] = first_line[:100]
            if code != 0:
                info["errors"].append(
                    f"scrcpy --version 退出码 {code}: {first_line[:200]}"
                )
        except Exception as exc:
            info["errors"].append(f"无法读取 scrcpy 版本：{exc}")
        try:
            code, output = await run_capture([scrcpy_path, "--help"], 20)
            info["supportedArgs"] = parse_supported_args(output)
            if code != 0:
                info["errors"].append(f"scrcpy --help 退出码 {code}")
        except Exception as exc:
            info["errors"].append(f"无法读取 scrcpy 参数表：{exc}")
    else:
        info["errors"].append("没有在 PATH 中找到 scrcpy。")

    if adb_path:
        try:
            code, output = await run_capture([adb_path, "version"], 12)
            first_line = next(
                (line.strip() for line in output.splitlines() if line.strip()), ""
            )
            info["adbVersion"] = first_line[:120] if first_line else None
            if code != 0:
                info["errors"].append(f"adb version 退出码 {code}")
        except Exception as exc:
            info["errors"].append(f"无法读取 adb 版本：{exc}")
    else:
        info["errors"].append("没有在 PATH 中找到 adb。")

    return info


def parse_adb_devices(output: str) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith("list of devices"):
            continue
        if line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial = parts[0]
        state = parts[1]
        if state == "no" and len(parts) > 2 and parts[2].startswith("permissions"):
            state = "no permissions"
        fields: dict[str, str] = {}
        for part in parts[2:]:
            if ":" in part:
                key, value = part.split(":", 1)
                fields[key] = value
        model = fields.get("model", "").replace("_", " ").strip()
        devices.append(
            {
                "serial": serial,
                "state": state,
                "model": model,
                "product": fields.get("product", "").replace("_", " "),
                "device": fields.get("device", ""),
                "transportId": fields.get("transport_id"),
                "usb": fields.get("usb"),
                "connection": "wireless" if ":" in serial else "usb",
                "androidVersion": None,
                "androidSdk": None,
                "manufacturer": "",
                "modelFromDevice": "",
            }
        )
    return devices


async def enrich_device(adb: str, device: dict[str, Any]) -> None:
    if device.get("state") != "device":
        return
    command = (
        "getprop ro.build.version.release; "
        "getprop ro.build.version.sdk; "
        "getprop ro.product.manufacturer; "
        "getprop ro.product.model; "
        "getprop ro.product.device"
    )
    try:
        code, output = await run_capture(
            [adb, "-s", str(device["serial"]), "shell", command], 15
        )
    except Exception:
        return
    if code != 0:
        return
    values = [line.strip() for line in output.replace("\r", "").split("\n")]
    values += [""] * (5 - len(values))
    version, sdk, manufacturer, model, product = values[:5]
    device["androidVersion"] = version or None
    with contextlib.suppress(ValueError):
        device["androidSdk"] = int(sdk) if sdk else None
    device["manufacturer"] = manufacturer
    device["modelFromDevice"] = model
    if model:
        device["model"] = model
    if product:
        device["device"] = product


# ---------------------------------------------------------------------------
# Scrcpy process runner
# ---------------------------------------------------------------------------


class ScrcpyRunner:
    def __init__(self, app: "AutoScrcpyApp") -> None:
        self.app = app
        self.process: subprocess.Popen[bytes] | None = None
        self.watch_task: asyncio.Task[None] | None = None
        self.stop_requested = False
        self.started_at = 0.0
        self.run_number = 0
        self.command = ""
        self.argv: list[str] = []

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def validate(self, argv: Any) -> tuple[list[str] | None, str | None]:
        if not isinstance(argv, list) or not argv or len(argv) > 200:
            return None, "命令格式不正确。"
        if not all(isinstance(arg, str) for arg in argv):
            return None, "命令参数必须是字符串。"
        clean = [arg for arg in argv]
        if Path(clean[0]).name.lower() not in {"scrcpy", "scrcpy.exe"}:
            return None, "后端只允许执行 scrcpy 命令。"
        if sum(len(arg) for arg in clean) > 32_000:
            return None, "命令参数过长。"
        return clean, None

    async def start(self, argv: Any, command: str = "") -> bool:
        if self.running:
            await self.app.send({"type": "error", "message": "scrcpy 已经在运行。"})
            return False
        clean, error = self.validate(argv)
        if error or clean is None:
            await self.app.send({"type": "error", "message": error or "命令无效。"})
            return False
        if not self.app.tools.get("scrcpyPath"):
            await self.app.send(
                {"type": "error", "message": "找不到 scrcpy，请检查 PATH。"}
            )
            return False

        executable = str(self.app.tools["scrcpyPath"])
        clean[0] = executable
        self.stop_requested = False
        self.run_number += 1
        self.started_at = time.time()
        self.command = command[:16_000]
        self.argv = list(clean)
        try:
            self.process = subprocess.Popen(
                clean,
                cwd=str(Path.home()),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=process_creation_flags(),
                bufsize=0,
            )
        except (OSError, ValueError) as exc:
            LOGGER.exception("Could not start scrcpy")
            self.process = None
            await self.app.send(
                {"type": "error", "message": f"启动 scrcpy 失败：{exc}"}
            )
            await self.app.send(
                {
                    "type": "run_finished",
                    "code": -1,
                    "duration": 0,
                    "stopped": False,
                    "message": f"启动失败：{exc}",
                }
            )
            return False

        await self.app.send(
            {
                "type": "run_started",
                "pid": self.process.pid,
                "runNumber": self.run_number,
                "command": self.command,
                "startedAt": self.started_at * 1000,
            }
        )
        self.watch_task = asyncio.create_task(self._watch(self.process))
        return True

    async def _watch(self, process: subprocess.Popen[bytes]) -> None:
        assert process.stdout is not None
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()

        def enqueue(item: bytes | None) -> None:
            try:
                queue.put_nowait(item)
            except RuntimeError:
                pass

        def read_output() -> None:
            stream = process.stdout
            assert stream is not None
            try:
                while True:
                    raw = stream.readline()
                    if not raw:
                        break
                    try:
                        loop.call_soon_threadsafe(enqueue, raw)
                    except RuntimeError:
                        return
            except Exception:
                LOGGER.debug("Output reader failed", exc_info=True)
            finally:
                with contextlib.suppress(RuntimeError):
                    loop.call_soon_threadsafe(enqueue, None)

        threading.Thread(target=read_output, name="scrcpy-output", daemon=True).start()

        try:
            while True:
                raw = await queue.get()
                if raw is None:
                    break
                text = strip_ansi(decode_bytes(raw)).rstrip("\r\n")
                if not text:
                    continue
                for piece in re.split(r"[\r\n]+", text):
                    piece = piece[:MAX_LOG_LINE].rstrip()
                    if piece:
                        await self.app.send(
                            {
                                "type": "run_output",
                                "lines": [{"text": piece, "ts": time.time() * 1000}],
                            }
                        )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.debug("Error while reading scrcpy output: %s", exc)

        try:
            code = await asyncio.to_thread(process.wait)
        except Exception:
            code = -1
        duration = max(0.0, time.time() - self.started_at)
        stopped = self.stop_requested
        if stopped:
            message = "已停止"
        elif code == 0:
            message = "scrcpy 已正常退出"
        elif code == 2:
            message = "设备连接已断开"
        elif code == 1:
            message = "scrcpy 启动失败，请查看下方日志"
        else:
            message = f"scrcpy 已退出（代码 {code}）"
        LOGGER.info(
            "scrcpy finished code=%s duration=%.2fs stopped=%s", code, duration, stopped
        )
        if self.process is process:
            self.process = None
        if self.watch_task is asyncio.current_task():
            self.watch_task = None
        await self.app.send(
            {
                "type": "run_finished",
                "code": code,
                "duration": duration,
                "stopped": stopped,
                "message": message,
            }
        )
        try:
            await self.app.maybe_restore_console()
        except Exception:
            LOGGER.exception("Could not restore the console after the run")

    async def stop(self, notify: bool = True) -> bool:
        process = self.process
        if process is None or process.poll() is not None:
            return False
        self.stop_requested = True
        if notify:
            await self.app.send(
                {"type": "run_status", "status": "stopping", "message": "正在停止…"}
            )
        with contextlib.suppress(Exception):
            process.terminate()
        for _ in range(50):
            if process.poll() is not None:
                return True
            await asyncio.sleep(0.1)
        with contextlib.suppress(Exception):
            process.kill()
        await asyncio.to_thread(process.wait)
        return True


# ---------------------------------------------------------------------------
# The application
# ---------------------------------------------------------------------------


class AutoScrcpyApp:
    def __init__(self, config_dir: Path, requested_port: int = 0) -> None:
        self.config_dir = config_dir
        self.settings_file = config_dir / "settings.json"
        self.profile_dir = config_dir / "browser-profile"
        self.requested_port = requested_port
        self.settings = load_settings(self.settings_file)
        self.window_state_file = config_dir / "window-state.json"
        self.window_state = load_window_state(self.window_state_file)
        self.window_state_lock = threading.Lock()
        self.tools: dict[str, Any] = {}
        self.server: Any = None
        self.sock: socket.socket | None = None
        self.port = 0
        self.url = ""
        self.client: ServerConnection | None = None
        self.client_lock = asyncio.Lock()
        self.send_lock = asyncio.Lock()
        self.settings_lock = asyncio.Lock()
        self.refresh_lock = asyncio.Lock()
        self.shutdown_lock = asyncio.Lock()
        self.window_lock = asyncio.Lock()
        self.exit_event = asyncio.Event()
        self.connected_event = asyncio.Event()
        self.shutting_down = False
        self.shutdown_reason = ""
        self.initial_timeout_task: asyncio.Task[None] | None = None
        self.disconnect_task: asyncio.Task[None] | None = None
        self.background_tasks: set[asyncio.Task[Any]] = set()
        self.runner = ScrcpyRunner(self)
        self.started_at = time.time()
        self.browser_process: subprocess.Popen[bytes] | None = None
        self.webview: webview_host.WebViewHost | None = None
        self.window_backend = "none"
        self.window_backend_pref = "auto"
        self.webview_info = ""
        self.console_detached = False
        self.tray: win_tray.TrayIcon | None = None
        self.tray_enabled = True
        self.loop: asyncio.AbstractEventLoop | None = None
        self.closing = False

    @property
    def tray_available(self) -> bool:
        return bool(self.tray and self.tray.available)

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.tools = await discover_tools()
        self.sock = allocate_socket(self.requested_port)
        self.port = int(self.sock.getsockname()[1])
        self.url = f"http://{HOST}:{self.port}/"
        origins = [
            f"http://{HOST}:{self.port}",
            f"http://localhost:{self.port}",
        ]
        self.server = await serve(
            self._handler,
            sock=self.sock,
            origins=origins,
            process_request=self._process_request,
            ping_interval=20,
            ping_timeout=15,
            close_timeout=3,
            max_size=MAX_MESSAGE,
            max_queue=32,
            compression="deflate",
            server_header=f"{APP_NAME}/{APP_VERSION}",
        )
        self.initial_timeout_task = asyncio.create_task(self._first_connect_timeout())
        LOGGER.info("Listening on %s", self.url)
        LOGGER.info(
            "scrcpy=%s adb=%s",
            self.tools.get("scrcpyPath"),
            self.tools.get("adbPath"),
        )

    async def _first_connect_timeout(self) -> None:
        await asyncio.sleep(FIRST_CONNECT_TIMEOUT)
        if self.client is None and not self.shutting_down:
            LOGGER.warning("No UI connected within %.0fs", FIRST_CONNECT_TIMEOUT)
            await self.request_shutdown("等待前端连接超时")

    def _spawn(self, awaitable: Any) -> asyncio.Task[Any]:
        task = asyncio.create_task(awaitable)
        self.background_tasks.add(task)

        def done(finished: asyncio.Task[Any]) -> None:
            self.background_tasks.discard(finished)
            if finished.cancelled():
                return
            error = finished.exception()
            if error:
                LOGGER.exception("Background task failed", exc_info=error)

        task.add_done_callback(done)
        return task

    async def request_shutdown(self, reason: str) -> None:
        async with self.shutdown_lock:
            if self.shutting_down:
                return
            self.shutting_down = True
            self.shutdown_reason = reason
        LOGGER.info("Shutdown requested: %s", reason)
        if self.disconnect_task and not self.disconnect_task.done():
            self.disconnect_task.cancel()
        if self.initial_timeout_task and not self.initial_timeout_task.done():
            self.initial_timeout_task.cancel()
        client = self.client
        if client is not None:
            with contextlib.suppress(Exception):
                await self._send_json(
                    {"type": "shutdown", "reason": reason}, target=client
                )
            with contextlib.suppress(Exception):
                await client.close(1001, reason[:100])
        with contextlib.suppress(Exception):
            await self.runner.stop(notify=False)
        self.exit_event.set()

    async def close(self) -> None:
        self.closing = True
        if self.server is not None:
            self.server.close()
            with contextlib.suppress(Exception):
                await self.server.wait_closed()
        if self.initial_timeout_task and not self.initial_timeout_task.done():
            self.initial_timeout_task.cancel()
        if self.disconnect_task and not self.disconnect_task.done():
            self.disconnect_task.cancel()
        for task in list(self.background_tasks):
            task.cancel()
        if self.background_tasks:
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        with contextlib.suppress(Exception):
            await self.runner.stop(notify=False)
        watch = self.runner.watch_task
        if watch and not watch.done():
            with contextlib.suppress(Exception):
                await asyncio.wait_for(asyncio.shield(watch), 3)
        if self.webview is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(self.webview.stop)
            self.webview = None
        if self.tray is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(self.tray.stop)
            self.tray = None

    # -- tray and console window ------------------------------------------

    def start_tray(self) -> None:
        """Create the notification-area icon; failure stays non-fatal."""
        if not self.tray_enabled or self.loop is None:
            return
        tray: win_tray.TrayIcon | None = None
        try:
            tray = win_tray.TrayIcon(
                icon_path=TRAY_ICON_DARK_PATH,
                light_icon_path=TRAY_ICON_LIGHT_PATH,
                tooltip=f"{APP_NAME} · 镜像控制台",
                on_open=lambda: self._tray_call(self.show_console),
                on_stop=lambda: self._tray_call(self.stop_from_tray),
                on_quit=lambda: self._tray_call(
                    lambda: self.request_shutdown("已从托盘退出")
                ),
                is_running=lambda: self.runner.running,
            )
            if tray.start():
                self.tray = tray
                LOGGER.info("Tray icon available")
            else:
                with contextlib.suppress(Exception):
                    tray.stop()
                LOGGER.warning("托盘图标不可用；「最小化到托盘」将回退为最小化控制台")
        except Exception:
            LOGGER.exception("Could not start the tray icon")
            if tray is not None:
                with contextlib.suppress(Exception):
                    tray.stop()

    def _tray_call(self, action: Callable[[], Awaitable[None]]) -> None:
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(lambda: asyncio.create_task(action()))

    def open_console_window(self) -> str:
        target, process = open_ui_window(self.url, self.profile_dir, False)
        if process is not None:
            self.browser_process = process
        return target

    def _window_close_from_host(self) -> None:
        """Called on the WebView2 thread when the user closes the window."""
        loop = self.loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self._handle_window_close())
        )

    async def _handle_window_close(self) -> None:
        if self.shutting_down or self.closing:
            return
        if self.settings.get("keepInBackground", True):
            # Closing the window means "keep running in the tray"; stop the
            # WebView front-end so it no longer consumes memory/CPU.
            await self._park_console_in_tray()
        else:
            await self.request_shutdown("已关闭窗口")

    def _remember_window_geometry(self, placement: dict[str, Any]) -> None:
        """Persist the WebView2 window geometry (called from its UI thread)."""
        with self.window_state_lock:
            if placement == self.window_state:
                return
            self.window_state = dict(placement)
            with contextlib.suppress(OSError):
                save_settings_atomic(self.window_state_file, self.window_state)

    def _open_webview_window(self) -> bool:
        available, info = webview_host.webview_available()
        self.webview_info = info
        if not available:
            LOGGER.info("WebView2 unavailable: %s", info)
            return False
        host = webview_host.WebViewHost(
            self.url,
            title=f"{APP_NAME} · 镜像控制台",
            icon_path=TRAY_ICON_PATH,
            user_data_dir=self.config_dir / "webview-profile",
            on_close=self._window_close_from_host,
            appearance=resolve_appearance(self.settings.get("appearance")),
            placement=self.window_state,
            on_geometry=self._remember_window_geometry,
        )
        # Publish the backend before navigation starts so the first `hello`
        # already reports "webview" to the page.
        self.webview = host
        self.window_backend = "webview"
        try:
            opened = host.start()
        except Exception:
            LOGGER.exception("Could not start the WebView2 window")
            opened = False
        if not opened:
            LOGGER.warning("WebView2 window failed: %s", host.error)
            host.stop(timeout=2.0)
            self.webview = None
            self.window_backend = "none"
            return False
        LOGGER.info("Opened UI with %s", info)
        return True

    async def open_main_window(self) -> str:
        """Prefer the in-process WebView2 window, fall back to a browser."""
        if self.window_backend_pref != "browser":
            opened = await asyncio.to_thread(self._open_webview_window)
            if opened:
                return "webview"
        target = await asyncio.to_thread(self.open_console_window)
        self.window_backend = "browser" if target not in {"disabled", "failed"} else "none"
        LOGGER.info("Opened UI via %s", target)
        if target == "failed":
            LOGGER.error("Could not open a window for %s", self.url)
        return target

    async def show_console(self) -> None:
        if self.shutting_down or self.closing:
            return
        async with self.window_lock:
            if self.shutting_down or self.closing:
                return
            if self.webview is not None and self.webview.running:
                self.console_detached = False
                self.webview.show_restore()
                return
            if self.window_backend == "webview":
                # The WebView2 window was stopped when it was parked in the
                # tray; recreate it now.
                opened = await asyncio.to_thread(self._open_webview_window)
                if opened and self.webview is not None:
                    self.console_detached = False
                    self.webview.show_restore()
                    return
            hwnd = await asyncio.to_thread(win_tray.find_console_window)
            if hwnd:
                await asyncio.to_thread(win_tray.restore_window, hwnd)
                return
            target = await asyncio.to_thread(self.open_console_window)
            LOGGER.info("Reopened console window via %s", target)
            if target == "failed":
                LOGGER.error("Could not reopen the console window")
                return
            if target != "disabled":
                # A browser started by a background process may only flash in
                # the taskbar instead of becoming visible; wait for its window
                # and explicitly restore/focus it.
                self._spawn(self._focus_reopened_console())

    async def _focus_reopened_console(self, timeout: float = 12.0) -> None:
        process = self.browser_process
        pid = int(getattr(process, "pid", 0) or 0)
        deadline = time.monotonic() + max(0.0, timeout)
        while not (self.closing or self.shutting_down):
            hwnd = 0
            if pid:
                hwnd = await asyncio.to_thread(win_tray.find_window_for_process, pid)
            if not hwnd:
                hwnd = await asyncio.to_thread(win_tray.find_console_window)
            if hwnd:
                restored = await asyncio.to_thread(win_tray.restore_window, hwnd)
                if restored:
                    LOGGER.info("Console window brought to the foreground")
                    return
            if time.monotonic() >= deadline:
                LOGGER.warning("控制台窗口已打开，但未能自动切到前台")
                return
            await asyncio.sleep(0.2)

    async def stop_from_tray(self) -> None:
        if self.runner.running:
            await self.runner.stop()

    async def _minimize_console_window(self) -> None:
        if self.webview is not None and self.webview.running:
            self.webview.minimize()
            return
        hwnd = await asyncio.to_thread(win_tray.find_console_window)
        if hwnd:
            await asyncio.to_thread(win_tray.minimize_window, hwnd)

    async def _park_console_in_tray(self) -> None:
        async with self.window_lock:
            await self._park_console_in_tray_locked()

    async def _park_console_in_tray_locked(self) -> None:
        if not self.tray_available:
            await self._minimize_console_window()
            return
        if self.webview is not None and self.webview.running:
            # Stop the whole WebView2 front-end (renderer + window) so a
            # tray-parked console costs only the small Python backend.  The
            # page is recreated on demand by show_console().
            self.console_detached = True
            host = self.webview
            self.webview = None
            LOGGER.info("Stopping the WebView2 front-end (tray)")
            await asyncio.to_thread(host.stop)
            if self.tray is not None:
                self.tray.notify(
                    f"{APP_NAME} 正在后台运行",
                    "控制台已关闭，双击托盘图标可重新打开。",
                )
            return
        # Set the flag before closing: the WebSocket disconnect that follows
        # must not trigger the "front-end went away" shutdown.
        self.console_detached = True
        process = self.browser_process
        closed = await asyncio.to_thread(win_tray.close_console_window, process)
        self.browser_process = None
        if not closed:
            # Keep the normal lifecycle: if the browser could not be closed,
            # minimize it instead and do not suppress the disconnect shutdown.
            self.console_detached = False
            LOGGER.warning("无法关闭控制台浏览器，改为最小化窗口")
            await self._minimize_console_window()
            return
        LOGGER.info("Console parked in the tray (browser closed=%s)", closed)
        if self.tray is not None:
            self.tray.notify(
                f"{APP_NAME} 正在后台运行",
                "控制台已关闭，双击托盘图标可重新打开。",
            )

    async def maybe_restore_console(self) -> None:
        """Bring the console back after a run ends, if the user opted in."""
        if self.closing or self.shutting_down:
            return
        if not self.settings.get("autoOpenConsole", True):
            return
        if CONSOLE_RESTORE_DELAY > 0:
            await asyncio.sleep(CONSOLE_RESTORE_DELAY)
        # A restart starts a new run right after run_finished; do not flash the
        # console open just to have the new run minimize/park it again.
        if self.closing or self.shutting_down or self.runner.running:
            return
        if self.webview is not None and self.webview.running:
            if self.console_detached or self.webview.minimized:
                self.console_detached = False
                self.webview.show_restore()
            return
        if self.console_detached:
            await self.show_console()
            return
        hwnd = await asyncio.to_thread(win_tray.find_console_window)
        if hwnd and await asyncio.to_thread(win_tray.is_minimized, hwnd):
            await asyncio.to_thread(win_tray.restore_window, hwnd)

    async def _after_start(self, action: Any) -> None:
        """Focus scrcpy, then apply the chosen console-window behaviour."""
        process = self.runner.process
        if process is None:
            return
        choice = (
            action
            if isinstance(action, str) and action in AFTER_START_ACTIONS
            else str(self.settings.get("afterStart") or "focus")
        )
        if choice not in AFTER_START_ACTIONS:
            choice = "focus"
        if win_tray.IS_WINDOWS and "--no-window" not in self.runner.argv:
            hwnd = 0
            deadline = time.monotonic() + 8.0
            while True:
                hwnd = await asyncio.to_thread(
                    win_tray.find_scrcpy_window, process.pid, 0.0
                )
                if hwnd or not self.runner.running:
                    break
                if time.monotonic() >= deadline:
                    break
                await asyncio.sleep(0.2)
            if hwnd:
                await asyncio.to_thread(win_tray.focus_window, hwnd)
            elif self.runner.running:
                LOGGER.warning("找不到 scrcpy 窗口（PID %s）", process.pid)
        # The run may have ended (or been restarted) while waiting.
        if self.runner.process is not process or not self.runner.running:
            return
        if choice == "minimize":
            await self._minimize_console_window()
        elif choice == "tray":
            await self._park_console_in_tray()

    def _schedule_disconnect_shutdown(self) -> None:
        if self.shutting_down or self.console_detached:
            return
        if (
            self.window_backend == "browser"
            and self.settings.get("keepInBackground", True)
        ):
            # The browser window cannot intercept its close button.  Honour
            # "keep in background" by keeping the backend alive and reopening
            # the window from the tray.
            self.console_detached = True
            LOGGER.info("Browser window went away; keeping the backend running")
            return
        if self.disconnect_task and not self.disconnect_task.done():
            return
        self.disconnect_task = asyncio.create_task(self._disconnect_grace())

    async def _disconnect_grace(self) -> None:
        await asyncio.sleep(RECONNECT_GRACE)
        if self.client is None and not self.shutting_down and not self.console_detached:
            LOGGER.info("Front-end did not reconnect within %.1fs", RECONNECT_GRACE)
            await self.request_shutdown("前端连接已断开")

    # -- HTTP static files ------------------------------------------------

    def _process_request(
        self, connection: ServerConnection, request: Request
    ) -> Response | None:
        path = unquote(urlsplit(request.path).path)
        is_websocket = request.headers.get("Upgrade", "").lower() == "websocket"

        if path == "/ws":
            if is_websocket:
                return None
            return self._http_response(
                426,
                "Upgrade Required",
                "此地址仅用于 WebSocket 连接。",
                "text/plain; charset=utf-8",
            )
        if is_websocket:
            return self._http_response(
                404, "Not Found", "未知的 WebSocket 地址。", "text/plain; charset=utf-8"
            )

        if path in {"/", "/index.html"}:
            target = UI_DIR / "index.html"
        elif path == "/favicon.ico":
            return self._http_response(
                204,
                "No Content",
                "",
                "image/x-icon",
            )
        elif path.startswith("/assets/"):
            target = (UI_DIR / path.lstrip("/")).resolve()
            if not target.is_relative_to(UI_DIR.resolve()):
                return self._http_response(
                    403,
                    "Forbidden",
                    "无权访问此文件。",
                    "text/plain; charset=utf-8",
                )
        else:
            return self._http_response(
                404, "Not Found", "页面不存在。", "text/plain; charset=utf-8"
            )

        if not target.is_file():
            return self._http_response(
                404,
                "Not Found",
                f"缺少前端文件：{target.name}",
                "text/plain; charset=utf-8",
            )
        try:
            body = target.read_bytes()
        except OSError as exc:
            LOGGER.exception("Could not read UI file %s", target)
            return self._http_response(
                500,
                "Internal Server Error",
                f"无法读取前端文件：{exc}",
                "text/plain; charset=utf-8",
            )

        content_type = (
            mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        )
        if target.suffix.lower() in {".html", ".css", ".js", ".svg"}:
            content_type += "; charset=utf-8"
        return self._http_response(
            200,
            "OK",
            body,
            content_type,
        )

    def _http_response(
        self,
        status: int,
        reason: str,
        body: str | bytes,
        content_type: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> Response:
        raw = body.encode("utf-8") if isinstance(body, str) else body
        headers = Headers()
        headers["Content-Type"] = content_type
        headers["Content-Length"] = str(len(raw))
        headers["Cache-Control"] = "no-store, max-age=0"
        headers["X-Content-Type-Options"] = "nosniff"
        headers["X-Frame-Options"] = "DENY"
        headers["Referrer-Policy"] = "no-referrer"
        headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self' ws://127.0.0.1:*; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        )
        if extra_headers:
            for key, value in extra_headers.items():
                headers[key] = value
        return Response(status, reason, headers, raw)

    # -- WebSocket connection --------------------------------------------

    async def _handler(self, websocket: ServerConnection) -> None:
        remote = getattr(websocket, "remote_address", None)
        LOGGER.info("UI connected from %s", remote)
        async with self.client_lock:
            previous = self.client
            self.client = websocket
        if previous is not None and previous is not websocket:
            LOGGER.info("Replacing previous UI connection")
            self._spawn(self._close_quietly(previous))

        if self.disconnect_task and not self.disconnect_task.done():
            self.disconnect_task.cancel()
        if self.initial_timeout_task and not self.initial_timeout_task.done():
            self.initial_timeout_task.cancel()
        self.console_detached = False
        self.connected_event.set()

        try:
            await self._send_hello(websocket)
            async for raw in websocket:
                await self._handle_client_message(raw)
        except ConnectionClosed:
            pass
        except Exception:
            LOGGER.exception("WebSocket handler failed")
        finally:
            if self.client is websocket:
                self.client = None
                LOGGER.info("UI disconnected")
                self._schedule_disconnect_shutdown()

    async def _close_quietly(self, websocket: ServerConnection) -> None:
        with contextlib.suppress(Exception):
            await websocket.close(1001, "replaced by a new page")

    async def _send_hello(self, websocket: ServerConnection) -> None:
        process = self.runner.process
        run_state = {
            "running": self.runner.running,
            "pid": process.pid if process is not None else None,
            "runNumber": self.runner.run_number,
            "startedAt": self.runner.started_at * 1000,
            "command": self.runner.command,
        }
        await self._send_json(
            {
                "type": "hello",
                "app": APP_NAME,
                "version": APP_VERSION,
                "pid": os.getpid(),
                "port": self.port,
                "url": self.url,
                "settings": self.settings,
                "tools": self.tools,
                "run": run_state,
                "systemScale": get_system_scale(),
                "reconnectGrace": RECONNECT_GRACE,
                "trayAvailable": self.tray_available,
                "windowBackend": self.window_backend,
                "webviewInfo": self.webview_info,
                "startedAt": self.started_at * 1000,
            },
            target=websocket,
        )

    async def _send_json(
        self, payload: dict[str, Any], target: ServerConnection | None = None
    ) -> bool:
        websocket = target or self.client
        if websocket is None:
            return False
        try:
            async with self.send_lock:
                await websocket.send(json_text(payload))
            return True
        except (ConnectionClosed, OSError):
            return False
        except Exception:
            LOGGER.debug("Could not send WebSocket message", exc_info=True)
            return False

    async def send(self, payload: dict[str, Any]) -> bool:
        return await self._send_json(payload)

    async def _handle_client_message(self, raw: str | bytes) -> None:
        if isinstance(raw, bytes):
            await self.send({"type": "error", "message": "不支持二进制消息。"})
            return
        try:
            message = json.loads(raw)
        except ValueError:
            await self.send({"type": "error", "message": "消息不是合法 JSON。"})
            return
        if not isinstance(message, dict):
            await self.send({"type": "error", "message": "消息格式不正确。"})
            return
        kind = message.get("type")
        if kind == "ping":
            await self.send({"type": "pong", "ts": time.time() * 1000})
        elif kind == "list_devices":
            self._spawn(self.refresh_devices())
        elif kind == "adb_connect":
            self._spawn(self._adb_connect(message.get("address")))
        elif kind == "adb_disconnect":
            self._spawn(self._adb_disconnect(message.get("serial")))
        elif kind == "run":
            started = await self.runner.start(
                message.get("argv"), str(message.get("command") or "")
            )
            if started:
                self._spawn(self._after_start(message.get("afterStart")))
        elif kind == "stop":
            await self.runner.stop()
        elif kind == "app_action":
            await self._handle_app_action(message.get("action"))
        elif kind == "save_settings":
            await self._save_settings(message.get("settings"))
        elif kind == "quit":
            await self.request_shutdown("已从界面退出")
        else:
            await self.send({"type": "error", "message": f"未知命令：{kind}"})

    async def _handle_app_action(self, action: Any) -> None:
        """Window-level actions requested by the top-right button."""
        if action == "quit":
            await self.request_shutdown("已从界面退出")
        elif action == "park":
            await self._park_console_in_tray()
        elif action == "minimize":
            await self._minimize_console_window()
        else:
            await self.send(
                {"type": "error", "message": f"未知的窗口操作：{action}"}
            )

    # -- adb operations ---------------------------------------------------

    async def refresh_devices(self) -> None:
        if self.refresh_lock.locked():
            return
        async with self.refresh_lock:
            await self.send({"type": "devices_loading"})
            adb = self.tools.get("adbPath")
            if not adb:
                await self.send(
                    {
                        "type": "devices",
                        "devices": [],
                        "error": "找不到 adb，请检查 PATH 或 Android Platform Tools。",
                        "fetchedAt": time.time() * 1000,
                    }
                )
                return
            try:
                code, output = await run_capture([adb, "devices", "-l"], 20)
            except Exception as exc:
                await self.send(
                    {
                        "type": "devices",
                        "devices": [],
                        "error": f"读取 adb 设备失败：{exc}",
                        "fetchedAt": time.time() * 1000,
                    }
                )
                return
            if code != 0:
                await self.send(
                    {
                        "type": "devices",
                        "devices": [],
                        "error": f"adb devices 退出码 {code}：{output.strip()[:500]}",
                        "fetchedAt": time.time() * 1000,
                    }
                )
                return
            devices = parse_adb_devices(output)
            await asyncio.gather(
                *(enrich_device(adb, device) for device in devices),
                return_exceptions=True,
            )
            devices.sort(
                key=lambda device: (
                    0 if device.get("state") == "device" else 1,
                    str(device.get("serial", "")).lower(),
                )
            )
            await self.send(
                {
                    "type": "devices",
                    "devices": devices,
                    "error": None,
                    "fetchedAt": time.time() * 1000,
                }
            )

    async def _adb_connect(self, address: Any) -> None:
        adb = self.tools.get("adbPath")
        if not adb:
            await self.send(
                {
                    "type": "adb_result",
                    "action": "connect",
                    "ok": False,
                    "message": "找不到 adb。",
                }
            )
            return
        if not isinstance(address, str) or not ADDRESS_RE.fullmatch(address.strip()):
            await self.send(
                {
                    "type": "adb_result",
                    "action": "connect",
                    "ok": False,
                    "message": "地址格式不正确，示例：192.168.5.60:5555",
                }
            )
            return
        address = address.strip()
        try:
            code, output = await run_capture([adb, "connect", address], 20)
        except Exception as exc:
            await self.send(
                {
                    "type": "adb_result",
                    "action": "connect",
                    "address": address,
                    "ok": False,
                    "message": f"连接失败：{exc}",
                }
            )
            return
        lowered = output.lower()
        ok = code == 0 and "connected to" in lowered and "failed" not in lowered
        message = output.strip() or ("已发起连接" if ok else f"adb 退出码 {code}")
        await self.send(
            {
                "type": "adb_result",
                "action": "connect",
                "address": address,
                "ok": ok,
                "message": message[:1000],
            }
        )
        await self.refresh_devices()

    async def _adb_disconnect(self, serial: Any) -> None:
        adb = self.tools.get("adbPath")
        if not adb:
            await self.send(
                {
                    "type": "adb_result",
                    "action": "disconnect",
                    "ok": False,
                    "message": "找不到 adb。",
                }
            )
            return
        if not isinstance(serial, str) or not ADDRESS_RE.fullmatch(serial.strip()):
            await self.send(
                {
                    "type": "adb_result",
                    "action": "disconnect",
                    "ok": False,
                    "message": "设备地址格式不正确。",
                }
            )
            return
        serial = serial.strip()
        try:
            code, output = await run_capture([adb, "disconnect", serial], 15)
        except Exception as exc:
            await self.send(
                {
                    "type": "adb_result",
                    "action": "disconnect",
                    "serial": serial,
                    "ok": False,
                    "message": f"断开失败：{exc}",
                }
            )
            return
        await self.send(
            {
                "type": "adb_result",
                "action": "disconnect",
                "serial": serial,
                "ok": code == 0,
                "message": (output.strip() or "已断开")[:1000],
            }
        )
        await self.refresh_devices()

    # -- settings ---------------------------------------------------------

    async def _save_settings(self, raw: Any) -> None:
        settings = sanitize_settings(raw)
        settings["updatedAt"] = max(
            int(settings.get("updatedAt") or 0), int(time.time() * 1000)
        )
        async with self.settings_lock:
            self.settings = settings
            if self.webview is not None:
                self.webview.set_appearance(
                    resolve_appearance(settings.get("appearance"))
                )
            try:
                await asyncio.to_thread(
                    save_settings_atomic, self.settings_file, settings
                )
            except OSError as exc:
                LOGGER.exception("Could not save settings")
                await self.send(
                    {
                        "type": "settings_error",
                        "message": f"无法保存设置：{exc}",
                    }
                )
                return
        await self.send(
            {
                "type": "settings_saved",
                "updatedAt": settings["updatedAt"],
            }
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def setup_logging(config_dir: Path, verbose: bool = False) -> Path:
    log_path = config_dir / "autoscrcpy.log"
    with contextlib.suppress(OSError):
        config_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = []
    with contextlib.suppress(OSError):
        handlers.append(
            RotatingFileHandler(
                log_path,
                maxBytes=1_500_000,
                backupCount=3,
                encoding="utf-8",
            )
        )
    if verbose and sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    if not handlers:
        handlers.append(logging.NullHandler())
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=handlers,
        force=True,
    )
    return log_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="AutoScrcpy",
        description="A local WebView2/browser UI for scrcpy.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the UI window (useful for debugging).",
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="Do not create the notification-area icon.",
    )
    parser.add_argument(
        "--window-backend",
        choices=sorted(WINDOW_BACKENDS),
        default="auto",
        help="Window backend: auto (WebView2 first), webview, or browser.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Use a fixed WebSocket/HTTP port instead of a random free one.",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Override the settings/log directory.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Write verbose logs to stderr as well.",
    )
    parser.add_argument(
        "--print-url",
        action="store_true",
        help="Print the UI URL to stdout (debugging).",
    )
    return parser.parse_args(argv)


async def async_main(args: argparse.Namespace) -> int:
    config_dir = (args.config_dir or default_config_dir()).expanduser().resolve()
    log_path = setup_logging(config_dir, args.verbose)
    LOGGER.info("Starting %s %s", APP_NAME, APP_VERSION)

    if not (UI_DIR / "index.html").is_file():
        raise FileNotFoundError(f"缺少前端文件：{UI_DIR / 'index.html'}")

    app = AutoScrcpyApp(config_dir, requested_port=args.port)
    app.tray_enabled = not args.no_tray
    app.window_backend_pref = args.window_backend
    await app.start()
    app.start_tray()
    if args.print_url:
        print(app.url, flush=True)

    if not args.no_browser:
        target = await app.open_main_window()
        if target == "failed":
            LOGGER.error("Could not open a window for %s", app.url)

    loop = asyncio.get_running_loop()

    def request_stop(signum: int) -> None:
        LOGGER.info("Received signal %s", signum)
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(app.request_shutdown("后端收到退出信号"))
        )

    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        with contextlib.suppress(Exception):
            loop.add_signal_handler(sig, request_stop, int(sig))

    try:
        await app.exit_event.wait()
    finally:
        await app.request_shutdown(app.shutdown_reason or "应用退出")
        await app.close()
    LOGGER.info("Stopped (log: %s)", log_path)
    return 0


def main() -> int:
    if os.name == "nt":
        with contextlib.suppress(Exception):
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        with contextlib.suppress(Exception):
            ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
        with contextlib.suppress(Exception):
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "AutoScrcpy.UI"
            )
    args = parse_args()
    try:
        return asyncio.run(async_main(args))
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        LOGGER.exception("Fatal error")
        config_dir = (args.config_dir or default_config_dir()).expanduser().resolve()
        show_native_error(
            f"{APP_NAME} 启动失败",
            f"{exc}\n\n详细日志：\n{config_dir / 'autoscrcpy.log'}",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
