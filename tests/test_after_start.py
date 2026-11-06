from __future__ import annotations

import asyncio
import io
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app  # noqa: E402
import win_tray  # noqa: E402


class FakeProcess:
    def __init__(self, pid: int = 4242, exit_code: int | None = None) -> None:
        self.pid = pid
        self.exit_code = exit_code

    def poll(self) -> int | None:
        return self.exit_code


class FakeTray:
    available = True

    def __init__(self) -> None:
        self.notes: list[tuple[str, str]] = []

    def notify(self, title: str, message: str) -> bool:
        self.notes.append((title, message))
        return True


class AfterStartTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = app.AutoScrcpyApp(Path(self.temp_dir.name))
        self.process = FakeProcess()
        self.app.runner.process = self.process
        self.app.runner.argv = ["scrcpy"]
        self._delay_patch = mock.patch.object(app, "CONSOLE_RESTORE_DELAY", 0)
        self._delay_patch.start()

    def tearDown(self) -> None:
        self._delay_patch.stop()
        self.app.runner.process = None
        self.temp_dir.cleanup()

    async def test_focus_only_brings_scrcpy_window_forward(self) -> None:
        order: list[tuple[str, int]] = []
        with (
            mock.patch.object(
                win_tray, "find_scrcpy_window", return_value=777
            ) as find_window,
            mock.patch.object(
                win_tray,
                "focus_window",
                side_effect=lambda hwnd: order.append(("focus", hwnd)) or True,
            ),
            mock.patch.object(
                win_tray,
                "minimize_window",
                side_effect=lambda hwnd: order.append(("minimize", hwnd)),
            ),
            mock.patch.object(
                win_tray,
                "close_console_window",
                side_effect=lambda process: order.append(("close", 0)) or True,
            ),
        ):
            await self.app._after_start("focus")

        find_window.assert_called_once()
        self.assertEqual(order, [("focus", 777)])

    async def test_minimize_focuses_scrcpy_then_minimizes_console(self) -> None:
        order: list[str] = []
        with (
            mock.patch.object(win_tray, "find_scrcpy_window", return_value=777),
            mock.patch.object(
                win_tray,
                "focus_window",
                side_effect=lambda hwnd: order.append("focus") or True,
            ),
            mock.patch.object(win_tray, "find_console_window", return_value=888),
            mock.patch.object(
                win_tray,
                "minimize_window",
                side_effect=lambda hwnd: order.append("minimize") or True,
            ),
        ):
            await self.app._after_start("minimize")

        self.assertEqual(order, ["focus", "minimize"])

    async def test_tray_focuses_scrcpy_then_closes_browser(self) -> None:
        order: list[str] = []
        tray = FakeTray()
        self.app.tray = tray
        with (
            mock.patch.object(win_tray, "find_scrcpy_window", return_value=777),
            mock.patch.object(
                win_tray,
                "focus_window",
                side_effect=lambda hwnd: order.append("focus") or True,
            ),
            mock.patch.object(
                win_tray,
                "close_console_window",
                side_effect=lambda process: order.append("close") or True,
            ),
        ):
            await self.app._after_start("tray")

        self.assertEqual(order, ["focus", "close"])
        self.assertTrue(self.app.console_detached)
        self.assertEqual(len(tray.notes), 1)
        self.assertIn("托盘", tray.notes[0][1])

    async def test_tray_without_tray_icon_falls_back_to_minimizing(self) -> None:
        order: list[str] = []
        self.app.tray = None
        with (
            mock.patch.object(win_tray, "find_scrcpy_window", return_value=777),
            mock.patch.object(
                win_tray,
                "focus_window",
                side_effect=lambda hwnd: order.append("focus") or True,
            ),
            mock.patch.object(win_tray, "find_console_window", return_value=888),
            mock.patch.object(
                win_tray,
                "minimize_window",
                side_effect=lambda hwnd: order.append("minimize") or True,
            ),
            mock.patch.object(
                win_tray, "close_console_window"
            ) as close_window,
        ):
            await self.app._after_start("tray")

        self.assertEqual(order, ["focus", "minimize"])
        close_window.assert_not_called()
        self.assertFalse(self.app.console_detached)

    async def test_tray_close_failure_restores_lifecycle(self) -> None:
        self.app.tray = FakeTray()
        order: list[str] = []
        with (
            mock.patch.object(win_tray, "find_scrcpy_window", return_value=777),
            mock.patch.object(win_tray, "focus_window", return_value=True),
            mock.patch.object(win_tray, "find_console_window", return_value=888),
            mock.patch.object(
                win_tray,
                "minimize_window",
                side_effect=lambda hwnd: order.append("minimize") or True,
            ),
            mock.patch.object(win_tray, "close_console_window", return_value=False),
        ):
            await self.app._after_start("tray")

        self.assertEqual(order, ["minimize"])
        self.assertFalse(self.app.console_detached)

    async def test_no_window_skips_focusing(self) -> None:
        self.app.runner.argv = ["scrcpy", "--no-window"]
        with (
            mock.patch.object(win_tray, "find_scrcpy_window") as find_window,
            mock.patch.object(win_tray, "focus_window") as focus_window,
        ):
            await self.app._after_start("focus")

        find_window.assert_not_called()
        focus_window.assert_not_called()

    async def test_finished_run_does_not_touch_the_console(self) -> None:
        self.app.runner.process = FakeProcess(exit_code=1)
        with (
            mock.patch.object(win_tray, "find_scrcpy_window", return_value=0),
            mock.patch.object(win_tray, "focus_window") as focus_window,
            mock.patch.object(win_tray, "minimize_window") as minimize_window,
            mock.patch.object(win_tray, "close_console_window") as close_window,
        ):
            await self.app._after_start("tray")

        focus_window.assert_not_called()
        minimize_window.assert_not_called()
        close_window.assert_not_called()
        self.assertFalse(self.app.console_detached)

    async def test_restore_console_when_parked(self) -> None:
        self.assertTrue(self.app.settings["autoOpenConsole"])
        self.app.runner.process = None
        self.app.console_detached = True
        with mock.patch.object(
            self.app, "show_console", new=mock.AsyncMock()
        ) as show_console:
            await self.app.maybe_restore_console()
        show_console.assert_awaited_once()

    async def test_restore_console_when_minimized(self) -> None:
        self.app.runner.process = None
        with (
            mock.patch.object(win_tray, "find_console_window", return_value=888),
            mock.patch.object(win_tray, "is_minimized", return_value=True),
            mock.patch.object(win_tray, "restore_window") as restore_window,
        ):
            await self.app.maybe_restore_console()
        restore_window.assert_called_once_with(888)

    async def test_visible_console_is_left_alone(self) -> None:
        self.app.runner.process = None
        with (
            mock.patch.object(win_tray, "find_console_window", return_value=888),
            mock.patch.object(win_tray, "is_minimized", return_value=False),
            mock.patch.object(win_tray, "restore_window") as restore_window,
        ):
            await self.app.maybe_restore_console()
        restore_window.assert_not_called()

    async def test_auto_open_can_be_disabled(self) -> None:
        self.app.settings["autoOpenConsole"] = False
        self.app.console_detached = True
        with mock.patch.object(
            self.app, "show_console", new=mock.AsyncMock()
        ) as show_console:
            await self.app.maybe_restore_console()
        show_console.assert_not_awaited()

    async def test_restore_skipped_when_a_new_run_is_active(self) -> None:
        self.app.console_detached = True
        self.app.runner.process = FakeProcess()
        with mock.patch.object(
            self.app, "show_console", new=mock.AsyncMock()
        ) as show_console:
            await self.app.maybe_restore_console()
        show_console.assert_not_awaited()

    async def test_restore_skipped_while_shutting_down_or_closing(self) -> None:
        self.app.console_detached = True
        self.app.shutting_down = True
        with mock.patch.object(
            self.app, "show_console", new=mock.AsyncMock()
        ) as show_console:
            await self.app.maybe_restore_console()
        show_console.assert_not_awaited()

        self.app.shutting_down = False
        self.app.closing = True
        with mock.patch.object(
            self.app, "show_console", new=mock.AsyncMock()
        ) as show_console:
            await self.app.maybe_restore_console()
        show_console.assert_not_awaited()

    async def test_reopened_console_is_restored_from_process(self) -> None:
        self.app.browser_process = FakeProcess(pid=4321)
        with (
            mock.patch.object(
                win_tray, "find_window_for_process", return_value=123
            ) as find_pid,
            mock.patch.object(win_tray, "find_console_window", return_value=0),
            mock.patch.object(
                win_tray, "restore_window", return_value=True
            ) as restore_window,
        ):
            await self.app._focus_reopened_console(timeout=0)
        find_pid.assert_called_with(4321)
        restore_window.assert_called_once_with(123)

    async def test_reopened_console_falls_back_to_title(self) -> None:
        self.app.browser_process = FakeProcess(pid=4321)
        with (
            mock.patch.object(
                win_tray, "find_window_for_process", return_value=0
            ),
            mock.patch.object(
                win_tray, "find_console_window", return_value=555
            ),
            mock.patch.object(
                win_tray, "restore_window", return_value=True
            ) as restore_window,
        ):
            await self.app._focus_reopened_console(timeout=0)
        restore_window.assert_called_once_with(555)

    async def test_show_console_schedules_focus_after_relaunch(self) -> None:
        with (
            mock.patch.object(win_tray, "find_console_window", return_value=0),
            mock.patch.object(
                self.app, "open_console_window", return_value="msedge"
            ),
            mock.patch.object(self.app, "_spawn") as spawn,
        ):
            await self.app.show_console()
        spawn.assert_called_once()
        pending = spawn.call_args.args[0]
        pending.close()


class RunnerRestoreHookTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_finished_triggers_console_restore(self) -> None:
        events: list[str] = []

        class FakeApp:
            async def send(self, payload: dict) -> bool:
                events.append(payload["type"])
                return True

            async def maybe_restore_console(self) -> None:
                events.append("restore")

        class FakeProcess:
            stdout = io.BytesIO(b"hello from scrcpy\n")

            def poll(self) -> int:
                return 0

            def wait(self) -> int:
                return 0

        runner = app.ScrcpyRunner(FakeApp())  # type: ignore[arg-type]
        runner.process = FakeProcess()
        runner.started_at = time.time()
        await runner._watch(runner.process)  # type: ignore[arg-type]

        self.assertEqual(events, ["run_output", "run_finished", "restore"])
        self.assertIsNone(runner.process)


if __name__ == "__main__":
    unittest.main()
