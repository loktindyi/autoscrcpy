from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

import websockets

ROOT = Path(__file__).resolve().parents[1]


class ServerSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.process = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "app.py"),
                "--no-browser",
                "--no-tray",
                "--print-url",
                "--config-dir",
                self.temp_dir.name,
            ],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        assert self.process.stdout is not None
        try:
            line = await asyncio.wait_for(
                asyncio.to_thread(self.process.stdout.readline), timeout=30
            )
        except Exception:
            self.process.kill()
            self.temp_dir.cleanup()
            raise
        self.url = line.strip()
        parts = urlsplit(self.url)
        self.port = parts.port
        self.assertTrue(self.url.startswith("http://127.0.0.1:"))

    async def asyncTearDown(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                await asyncio.to_thread(self.process.wait, 5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                await asyncio.to_thread(self.process.wait, 5)
        if self.process.stdout is not None:
            self.process.stdout.close()
        self.temp_dir.cleanup()

    async def test_static_ws_settings_and_clean_exit(self) -> None:
        response = await asyncio.to_thread(
            urllib.request.urlopen, self.url + "assets/app.js", timeout=10
        )
        javascript = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("AutoScrcpy", javascript)
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))

        index = await asyncio.to_thread(
            urllib.request.urlopen, self.url, timeout=10
        )
        html = index.read().decode("utf-8")
        self.assertIn("镜像控制台", html)
        self.assertIn("Content-Security-Policy", index.headers)

        with self.assertRaises(urllib.error.HTTPError) as raised:
            await asyncio.to_thread(
                urllib.request.urlopen,
                self.url + "assets/../app.py",
                timeout=10,
            )
        self.assertEqual(raised.exception.code, 404)

        ws_url = f"ws://127.0.0.1:{self.port}/ws"
        origin = f"http://127.0.0.1:{self.port}"
        async with websockets.connect(ws_url, origin=origin) as websocket:
            hello = json.loads(await asyncio.wait_for(websocket.recv(), 15))
            self.assertEqual(hello["type"], "hello")
            self.assertEqual(hello["port"], self.port)
            self.assertIn("settings", hello)
            self.assertIn("tools", hello)
            self.assertIn("systemScale", hello)
            self.assertIn("trayAvailable", hello)
            self.assertIn("windowBackend", hello)

            await websocket.send(
                json.dumps(
                    {
                        "type": "save_settings",
                        "settings": {
                            "accent": "amber",
                            "appearance": "light",
                            "uiScale": "250",
                            "afterStart": "tray",
                            "autoOpenConsole": False,
                            "keepInBackground": False,
                            "selectedDevice": "device-1",
                            "options": {"maxSize": "1024"},
                            "extraArgs": "--no-mipmaps",
                            "profiles": [
                                {
                                    "id": "cfg-1",
                                    "name": "测试配置",
                                    "updatedAt": 123,
                                    "options": {"noAudio": True},
                                    "extraArgs": "--no-key-repeat",
                                }
                            ],
                            "lastProfile": {
                                "updatedAt": 456,
                                "command": "scrcpy --version",
                                "options": {"stayAwake": True},
                                "argv": ["scrcpy", "--version"],
                            },
                        },
                    }
                )
            )
            while True:
                message = json.loads(await asyncio.wait_for(websocket.recv(), 15))
                if message["type"] == "settings_saved":
                    break
            saved = json.loads(
                (Path(self.temp_dir.name) / "settings.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(saved["accent"], "amber")
            self.assertEqual(saved["appearance"], "light")
            self.assertEqual(saved["uiScale"], "250")
            self.assertEqual(saved["afterStart"], "tray")
            self.assertIs(saved["autoOpenConsole"], False)
            self.assertIs(saved["keepInBackground"], False)
            self.assertEqual(saved["selectedDevice"], "device-1")
            self.assertEqual(saved["options"]["maxSize"], "1024")
            self.assertEqual(saved["extraArgs"], "--no-mipmaps")
            self.assertEqual(saved["profiles"][0]["name"], "测试配置")
            self.assertEqual(
                saved["profiles"][0]["extraArgs"], "--no-key-repeat"
            )
            self.assertEqual(saved["lastProfile"]["name"], "上一次")
            self.assertEqual(
                saved["lastProfile"]["argv"], ["scrcpy", "--version"]
            )

        # Closing the only front-end must stop the backend after the grace period.
        return_code = await asyncio.wait_for(
            asyncio.to_thread(self.process.wait), timeout=15
        )
        self.assertEqual(return_code, 0)

    async def test_wrong_origin_is_rejected(self) -> None:
        ws_url = f"ws://127.0.0.1:{self.port}/ws"
        with self.assertRaises(Exception):
            async with websockets.connect(
                ws_url, origin="http://evil.example", open_timeout=5
            ):
                pass


if __name__ == "__main__":
    unittest.main()
