from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:  # Pillow is only needed for the pixel-level symmetry check.
    from PIL import Image
except ImportError:  # pragma: no cover - optional development dependency
    Image = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import win_tray  # noqa: E402

ASSETS = ROOT / "assets"


def ico_sizes(path: Path) -> set[tuple[int, int]]:
    data = path.read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    if reserved != 0 or kind != 1:
        raise ValueError("not an ICO file")
    sizes: set[tuple[int, int]] = set()
    for index in range(count):
        offset = 6 + index * 16
        width = data[offset] or 256
        height = data[offset + 1] or 256
        sizes.add((width, height))
    return sizes


class TrayIconAssetsTests(unittest.TestCase):
    def test_adaptive_ico_files_are_complete(self) -> None:
        for name in ("tray-dark.ico", "tray-light.ico"):
            path = ASSETS / name
            self.assertTrue(path.is_file(), name)
            sizes = ico_sizes(path)
            for expected in (16, 20, 24, 32, 48, 256):
                self.assertIn((expected, expected), sizes, name)

    def test_theme_helper_returns_valid_value(self) -> None:
        self.assertIn(win_tray.tray_theme(), {"light", "dark"})
        self.assertIn(win_tray.system_uses_light_theme(), {True, False})


class WindowIconSymmetryTests(unittest.TestCase):
    @unittest.skipIf(Image is None, "Pillow is not installed")
    def test_window_icon_ink_is_horizontally_centered(self) -> None:
        icon = Image.open(ASSETS / "autoscrcpy.ico")
        icon.size = (256, 256)
        pixels = icon.convert("RGBA")
        pixels.load()
        ink_x: list[int] = []
        for y in range(256):
            for x in range(256):
                r, g, b, a = pixels.getpixel((x, y))
                if a >= 200 and r + g + b >= 80:
                    ink_x.append(x)
        self.assertTrue(ink_x, "no artwork pixels found")
        left, right = min(ink_x), max(ink_x)
        self.assertLessEqual(abs((left + right) / 2 - 128), 1.5)
        self.assertLessEqual(abs(left - (255 - right)), 2)
        # The outer wave must not be pressed against the tile edge.
        self.assertGreaterEqual(left, 16)
        self.assertLessEqual(right, 239)


class TrayIconThemeSelectionTests(unittest.TestCase):
    def make_tray(self, light: Path | None) -> win_tray.TrayIcon:
        return win_tray.TrayIcon(
            icon_path=ASSETS / "tray-dark.ico",
            light_icon_path=light,
            tooltip="test",
            on_open=lambda: None,
            on_quit=lambda: None,
        )

    def test_icon_follows_requested_theme(self) -> None:
        tray = self.make_tray(ASSETS / "tray-light.ico")
        self.assertEqual(
            tray._icon_for_theme("light"), ASSETS / "tray-light.ico"
        )
        self.assertEqual(
            tray._icon_for_theme("dark"), ASSETS / "tray-dark.ico"
        )

    def test_missing_light_icon_falls_back_to_dark(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.ico"
            tray = self.make_tray(missing)
            self.assertEqual(
                tray._icon_for_theme("light"), ASSETS / "tray-dark.ico"
            )


class _FakeShell32:
    """Minimal stand-in for shell32.Shell_NotifyIconW."""

    def __init__(self, results: list[bool]) -> None:
        self.results = results
        self.flags: list[int] = []

    def Shell_NotifyIconW(self, flag: int, data) -> bool:  # noqa: ANN001
        self.flags.append(flag)
        return self.results.pop(0)


class TrayIconTaskbarRestoreTests(unittest.TestCase):
    def make_tray(self) -> win_tray.TrayIcon:
        tray = win_tray.TrayIcon(
            icon_path=ASSETS / "tray-dark.ico",
            light_icon_path=ASSETS / "tray-light.ico",
            tooltip="test",
            on_open=lambda: None,
            on_quit=lambda: None,
        )
        tray._hwnd = 1
        tray._load_icon = lambda: 42  # type: ignore[method-assign]
        return tray

    def test_dispatch_restores_on_taskbar_created(self) -> None:
        tray = self.make_tray()
        calls: list[str] = []
        tray._restore_taskbar_icon = lambda: calls.append("restored")  # type: ignore[method-assign]
        tray._taskbar_created = 0xC0BE
        self.assertEqual(
            tray._handle_message(0, 0xC0BE, 0, 0), 0
        )
        self.assertEqual(calls, ["restored"])

    def test_dispatch_restores_on_retry_timer(self) -> None:
        tray = self.make_tray()
        calls: list[str] = []
        tray._restore_taskbar_icon = lambda: calls.append("restored")  # type: ignore[method-assign]
        self.assertEqual(
            tray._handle_message(
                0, win_tray.WM_TIMER, win_tray.TASKBAR_RESTORE_TIMER, 0
            ),
            0,
        )
        self.assertEqual(calls, ["restored"])

    @unittest.skipUnless(win_tray.IS_WINDOWS, "Win32 tray icon only")
    def test_restore_uses_modify_when_add_fails(self) -> None:
        tray = self.make_tray()
        shell = _FakeShell32([False, True])
        user32 = mock.Mock()
        with mock.patch.object(win_tray, "_shell32", shell), mock.patch.object(
            win_tray, "_user32", user32
        ):
            tray._restore_taskbar_icon()
        self.assertEqual(
            shell.flags, [win_tray.NIM_ADD, win_tray.NIM_MODIFY]
        )
        self.assertEqual(tray._restore_attempts, 0)
        user32.SetTimer.assert_not_called()

    @unittest.skipUnless(win_tray.IS_WINDOWS, "Win32 tray icon only")
    def test_restore_failure_schedules_retry_timer(self) -> None:
        tray = self.make_tray()
        shell = _FakeShell32([False, False])
        user32 = mock.Mock()
        with mock.patch.object(win_tray, "_shell32", shell), mock.patch.object(
            win_tray, "_user32", user32
        ):
            tray._restore_taskbar_icon()
        self.assertEqual(tray._restore_attempts, 1)
        user32.SetTimer.assert_called_once_with(
            tray._hwnd,
            win_tray.TASKBAR_RESTORE_TIMER,
            win_tray.TASKBAR_RESTORE_INTERVAL_MS,
            None,
        )



if __name__ == "__main__":
    unittest.main()
