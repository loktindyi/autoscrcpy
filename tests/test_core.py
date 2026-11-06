from __future__ import annotations

import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app  # noqa: E402


class AdbParsingTests(unittest.TestCase):
    def test_parse_devices_mixed_states_and_fields(self) -> None:
        output = """List of devices attached
192.168.5.60:6728      device product:oppen model:X98plus device:oppen transport_id:1
R58M123456             unauthorized usb:1-1 transport_id:2
emulator-5554          offline
"""

        devices = app.parse_adb_devices(output)

        self.assertEqual(len(devices), 3)
        wireless = devices[0]
        self.assertEqual(wireless["serial"], "192.168.5.60:6728")
        self.assertEqual(wireless["state"], "device")
        self.assertEqual(wireless["model"], "X98plus")
        self.assertEqual(wireless["product"], "oppen")
        self.assertEqual(wireless["transportId"], "1")
        self.assertEqual(wireless["connection"], "wireless")
        self.assertEqual(devices[1]["state"], "unauthorized")
        self.assertEqual(devices[1]["connection"], "usb")
        self.assertEqual(devices[2]["state"], "offline")

    def test_parse_no_permissions_and_daemon_lines(self) -> None:
        output = """* daemon not running; starting now at tcp:5037
* daemon started successfully
List of devices attached
abc123    no permissions (user in plugdev group); see https://example.invalid
"""
        devices = app.parse_adb_devices(output)
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["state"], "no permissions")


class ScrcpyHelpParsingTests(unittest.TestCase):
    def test_supported_args_include_hwdec(self) -> None:
        output = """Usage: scrcpy [options]

    --hwdec=mode          Configure hardware video decoding on the computer.
                          Possible values are auto, disabled, d3d11va.
    --no-audio            Disable audio forwarding.
        --ignored         wrapped description lines are not option lines
"""
        self.assertEqual(
            app.parse_supported_args(output), ["--hwdec", "--no-audio"]
        )

    def test_help_without_new_options_has_no_hwdec(self) -> None:
        output = """Usage: scrcpy [options]

    -b, --video-bit-rate=rate
    --no-audio            Disable audio forwarding.
"""
        self.assertEqual(
            app.parse_supported_args(output),
            ["--no-audio", "--video-bit-rate"],
        )


class SettingsTests(unittest.TestCase):
    def test_sanitize_bounds_and_unknown_values(self) -> None:
        raw = {
            "accent": "not-a-colour",
            "uiScale": "150",
            "selectedDevice": "x" * 400,
            "collapsedSections": ["video", "video", 9],
            "options": {
                "maxSize": "1920",
                "noAudio": True,
                "count": 3,
                "nested": {"not": "allowed"},
            },
            "unknown": "ignored",
        }

        settings = app.sanitize_settings(raw)

        self.assertEqual(settings["accent"], "teal")
        self.assertNotIn("theme", settings)
        self.assertEqual(settings["uiScale"], "150")
        self.assertEqual(len(settings["selectedDevice"]), 300)
        self.assertEqual(settings["collapsedSections"], ["video"])
        self.assertEqual(settings["options"]["maxSize"], "1920")
        self.assertIs(settings["options"]["noAudio"], True)
        self.assertEqual(settings["options"]["count"], 3)
        self.assertNotIn("nested", settings["options"])
        self.assertNotIn("unknown", settings)

    def test_accent_choices_and_legacy_theme_migration(self) -> None:
        for accent in app.ACCENTS:
            self.assertEqual(
                app.sanitize_settings({"accent": accent})["accent"], accent
            )
        self.assertEqual(app.sanitize_settings({})["accent"], "teal")
        self.assertEqual(
            app.sanitize_settings({"accent": "neon"})["accent"], "teal"
        )
        self.assertEqual(
            app.sanitize_settings({"theme": "ember"})["accent"], "amber"
        )
        self.assertEqual(
            app.sanitize_settings({"theme": "paper"})["accent"], "slate"
        )
        self.assertEqual(
            app.sanitize_settings({"accent": "rose", "theme": "paper"})["accent"],
            "rose",
        )

    def test_keep_in_background_is_bounded(self) -> None:
        self.assertIs(app.sanitize_settings({})["keepInBackground"], True)
        self.assertIs(
            app.sanitize_settings({"keepInBackground": False})[
                "keepInBackground"
            ],
            False,
        )
        self.assertIs(
            app.sanitize_settings({"keepInBackground": "no"})[
                "keepInBackground"
            ],
            True,
        )

    def test_appearance_is_bounded(self) -> None:
        self.assertEqual(app.sanitize_settings({})["appearance"], "system")
        for choice in ("light", "dark", "system"):
            self.assertEqual(
                app.sanitize_settings({"appearance": choice})["appearance"],
                choice,
            )
        self.assertEqual(
            app.sanitize_settings({"appearance": "sepia"})["appearance"],
            "system",
        )
        self.assertIn(app.system_appearance(), {"light", "dark"})
        self.assertEqual(app.resolve_appearance("light"), "light")
        self.assertEqual(app.resolve_appearance("dark"), "dark")
        self.assertEqual(
            app.resolve_appearance("system"), app.system_appearance()
        )
        self.assertEqual(app.resolve_appearance("nonsense"), app.system_appearance())

    def test_extra_args_are_bounded(self) -> None:
        settings = app.sanitize_settings({"extraArgs": "x" * 5000})
        self.assertEqual(len(settings["extraArgs"]), 4000)
        self.assertEqual(
            app.sanitize_settings({"extraArgs": 3})["extraArgs"], ""
        )

    def test_profiles_and_last_profile_are_sanitized(self) -> None:
        settings = app.sanitize_settings(
            {
                "profiles": [
                    {
                        "id": "cfg-1",
                        "name": "夜间录制",
                        "selectedDevice": "device-1",
                        "deviceLabel": "X98plus",
                        "command": "scrcpy --version",
                        "optionCount": 4,
                        "options": {"noAudio": True, "maxSize": "1024"},
                        "extraArgs": "--no-mipmaps",
                        "argv": ["scrcpy", "--version"],
                    },
                    {"id": "cfg-2", "name": "上一次"},
                    {"id": "cfg-1", "name": "重复 ID"},
                    {"id": "cfg-3", "name": ""},
                ],
                "lastProfile": {
                    "name": "用户随便写的名字",
                    "selectedDevice": "device-1",
                    "command": "scrcpy --version",
                    "optionCount": 2,
                    "options": {"stayAwake": True},
                    "argv": ["scrcpy", "--version"],
                },
            }
        )

        self.assertEqual([p["name"] for p in settings["profiles"]], ["夜间录制"])
        self.assertEqual(settings["profiles"][0]["options"]["maxSize"], "1024")
        self.assertEqual(settings["profiles"][0]["extraArgs"], "--no-mipmaps")
        self.assertEqual(settings["lastProfile"]["id"], "last")
        self.assertEqual(settings["lastProfile"]["name"], "上一次")
        self.assertEqual(
            settings["lastProfile"]["argv"], ["scrcpy", "--version"]
        )

    def test_ui_scale_is_bounded(self) -> None:
        self.assertEqual(
            app.sanitize_settings({"uiScale": "system"})["uiScale"], "system"
        )
        self.assertEqual(
            app.sanitize_settings({"uiScale": "250"})["uiScale"], "250"
        )
        self.assertEqual(
            app.sanitize_settings({"uiScale": "75"})["uiScale"], "75"
        )
        self.assertEqual(
            app.sanitize_settings({"uiScale": "260"})["uiScale"], "system"
        )
        self.assertEqual(
            app.sanitize_settings({"uiScale": "abc"})["uiScale"], "system"
        )

    def test_after_start_choice_is_bounded(self) -> None:
        self.assertEqual(
            app.sanitize_settings({})["afterStart"], "focus"
        )
        for choice in ("focus", "minimize", "tray"):
            self.assertEqual(
                app.sanitize_settings({"afterStart": choice})["afterStart"],
                choice,
            )
        self.assertEqual(
            app.sanitize_settings({"afterStart": "explode"})["afterStart"],
            "focus",
        )

    def test_auto_open_console_setting_is_bounded(self) -> None:
        self.assertIs(app.sanitize_settings({})["autoOpenConsole"], True)
        self.assertIs(
            app.sanitize_settings({"autoOpenConsole": False})["autoOpenConsole"],
            False,
        )
        self.assertIs(
            app.sanitize_settings({"autoOpenConsole": "no"})["autoOpenConsole"],
            True,
        )

    def test_empty_last_profile_is_ignored(self) -> None:
        settings = app.sanitize_settings({"lastProfile": {}})
        self.assertIsNone(settings["lastProfile"])

    def test_atomic_save_and_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = app.sanitize_settings(
                {
                    "theme": "terminal",
                    "appearance": "light",
                    "selectedDevice": "192.168.5.60:6728",
                    "options": {"stayAwake": True, "maxSize": "1024"},
                    "extraArgs": "--no-mipmaps",
                    "keepInBackground": False,
                }
            )
            app.save_settings_atomic(path, settings)
            loaded = app.load_settings(path)
            self.assertEqual(loaded["accent"], "lime")
            self.assertEqual(loaded["appearance"], "light")
            self.assertEqual(loaded["selectedDevice"], "192.168.5.60:6728")
            self.assertEqual(loaded["options"]["maxSize"], "1024")
            self.assertEqual(loaded["extraArgs"], "--no-mipmaps")
            self.assertIs(loaded["keepInBackground"], False)
            self.assertTrue(path.read_text(encoding="utf-8").startswith("{"))
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["accent"], "lime"
            )


class ProcessSafetyTests(unittest.TestCase):
    def test_runner_rejects_non_scrcpy_commands(self) -> None:
        runner = app.ScrcpyRunner(None)  # type: ignore[arg-type]
        clean, error = runner.validate(["python", "-c", "print(1)"])
        self.assertIsNone(clean)
        self.assertIn("scrcpy", error or "")

    def test_runner_accepts_scrcpy_and_rejects_bad_shapes(self) -> None:
        runner = app.ScrcpyRunner(None)  # type: ignore[arg-type]
        clean, error = runner.validate(["scrcpy", "--version"])
        self.assertEqual(clean, ["scrcpy", "--version"])
        self.assertIsNone(error)
        self.assertIsNotNone(runner.validate([])[1])
        self.assertIsNotNone(runner.validate(["scrcpy", 3])[1])
        self.assertIsNotNone(runner.validate("scrcpy --version")[1])

    def test_allocate_socket_returns_usable_ephemeral_port(self) -> None:
        sock = app.allocate_socket(0)
        try:
            host, port = sock.getsockname()
            self.assertEqual(host, "127.0.0.1")
            self.assertGreater(port, 0)
            self.assertEqual(sock.family, socket.AF_INET)
        finally:
            sock.close()

    def test_open_ui_window_disabled_returns_process_pair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target, process = app.open_ui_window(
                "http://127.0.0.1:1/", Path(directory), True
            )
        self.assertEqual(target, "disabled")
        self.assertIsNone(process)


if __name__ == "__main__":
    unittest.main()
