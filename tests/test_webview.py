from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app  # noqa: E402
import webview_host  # noqa: E402


class WebViewAssetsTests(unittest.TestCase):
    def test_bundled_loader_matches_this_interpreter(self) -> None:
        path = webview_host.loader_path()
        self.assertIsNotNone(path)
        assert path is not None
        self.assertTrue(path.is_file())
        expected_bits = 64 if struct.calcsize("P") * 8 >= 64 else 32
        if sys.platform == "win32":
            self.assertEqual(path.name, f"WebView2Loader-x{expected_bits}.dll")

    def test_availability_returns_reason(self) -> None:
        available, reason = webview_host.webview_available()
        self.assertIsInstance(available, bool)
        self.assertTrue(reason)
        if not webview_host.IS_WINDOWS:
            self.assertFalse(available)

    def test_window_backend_cli_choice(self) -> None:
        args = app.parse_args(["--window-backend", "browser"])
        self.assertEqual(args.window_backend, "browser")
        args = app.parse_args([])
        self.assertEqual(args.window_backend, "auto")
        with self.assertRaises(SystemExit):
            app.parse_args(["--window-backend", "nope"])

    def test_devtools_cli_flag(self) -> None:
        self.assertFalse(app.parse_args([]).devtools)
        self.assertTrue(app.parse_args(["--devtools"]).devtools)


class WebViewHostStateTests(unittest.TestCase):
    def test_host_is_inert_before_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            host = webview_host.WebViewHost(
                "http://127.0.0.1:1/",
                title="test",
                icon_path=None,
                user_data_dir=Path(directory) / "profile",
            )
            self.assertFalse(host.available)
            self.assertFalse(host.running)
            self.assertFalse(host.minimized)
            self.assertFalse(host.visible)
            host.set_appearance("light")
            host.set_appearance("dark")
            host.show_restore()
            host.hide()
            host.minimize()
            host.focus()
            host.stop(timeout=0.2)
            self.assertFalse(host.running)


    def test_host_accepts_saved_placement_before_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            seen: list[dict] = []
            host = webview_host.WebViewHost(
                "http://127.0.0.1:1/",
                title="test",
                icon_path=None,
                user_data_dir=Path(directory) / "profile",
                placement={
                    "x": 80,
                    "y": 60,
                    "width": 1200,
                    "height": 800,
                    "maximized": True,
                },
                on_geometry=seen.append,
            )
            self.assertFalse(host.available)
            host.stop(timeout=0.2)
            self.assertEqual(seen, [])


if __name__ == "__main__":
    unittest.main()
