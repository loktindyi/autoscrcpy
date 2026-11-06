from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
_LOADER = SourceFileLoader("autoscrcpy_launcher", str(ROOT / "launch.pyw"))
_SPEC = importlib.util.spec_from_loader(_LOADER.name, _LOADER)
assert _SPEC is not None
launcher = importlib.util.module_from_spec(_SPEC)
sys.modules[_LOADER.name] = launcher
_LOADER.exec_module(launcher)


class LauncherCommandTests(unittest.TestCase):
    def test_launcher_has_no_shebang(self) -> None:
        # pyw.exe rejects "#!/usr/bin/env pythonw" with exit code 103, which
        # would make double-clicking the launcher do nothing at all.
        first_line = (ROOT / "launch.pyw").read_text(encoding="utf-8").splitlines()[0]
        self.assertFalse(first_line.startswith("#!"))

    def test_build_command_keeps_arguments_separate(self) -> None:
        command = launcher.build_command(
            Path("C:/Python/pythonw.exe"),
            Path("E:/AutoScrcpy/app.py"),
            ["--port", "8765", "--no-tray"],
        )
        self.assertEqual(
            command,
            [
                str(Path("C:/Python/pythonw.exe")),
                str(Path("E:/AutoScrcpy/app.py")),
                "--port",
                "8765",
                "--no-tray",
            ],
        )

    def test_main_starts_app_with_no_console_flag(self) -> None:
        process = mock.Mock()
        process.wait.return_value = 0
        executable = Path("C:/Python/pythonw.exe")
        with (
            mock.patch.object(
                launcher, "pythonw_executable", return_value=executable
            ),
            mock.patch.object(
                launcher.subprocess, "Popen", return_value=process
            ) as popen,
        ):
            self.assertEqual(launcher.main(["--no-tray"]), 0)

        command = popen.call_args.args[0]
        options = popen.call_args.kwargs
        self.assertEqual(
            command,
            [str(executable), str(launcher.APP_SCRIPT), "--no-tray"],
        )
        self.assertEqual(options["creationflags"], launcher.CREATE_NO_WINDOW)
        self.assertEqual(options["cwd"], str(launcher.BASE_DIR))
        self.assertEqual(options["stdin"], launcher.subprocess.DEVNULL)

    def test_early_failure_shows_the_log_hint(self) -> None:
        process = mock.Mock()
        process.wait.return_value = 2
        with (
            mock.patch.object(
                launcher, "pythonw_executable", return_value=Path("pythonw.exe")
            ),
            mock.patch.object(launcher.subprocess, "Popen", return_value=process),
            mock.patch.object(launcher, "show_error") as show_error,
        ):
            self.assertEqual(launcher.main([]), 2)

        show_error.assert_called_once()
        self.assertIn(launcher.LOG_PATH, show_error.call_args.args[0])

    def test_missing_app_script_is_reported(self) -> None:
        missing = Path(tempfile.gettempdir()) / "autoscrcpy-missing-app.py"
        with (
            mock.patch.object(launcher, "APP_SCRIPT", missing),
            mock.patch.object(launcher, "show_error") as show_error,
        ):
            self.assertEqual(launcher.main([]), 1)

        show_error.assert_called_once()
        self.assertIn("app.py", show_error.call_args.args[0])


class LauncherInterpreterTests(unittest.TestCase):
    def test_prefers_pythonw_from_path(self) -> None:
        with mock.patch.object(
            launcher.shutil, "which", return_value=r"C:\Path\pythonw.exe"
        ):
            executable = launcher.pythonw_executable(r"D:\Other\python.exe")

        self.assertEqual(executable, Path(r"C:\Path\pythonw.exe"))

    def test_prefers_pythonw_next_to_python(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            python = root / "python.exe"
            pythonw = root / "pythonw.exe"
            python.write_bytes(b"")
            pythonw.write_bytes(b"")
            with mock.patch.object(launcher.shutil, "which", return_value=None):
                self.assertEqual(launcher.pythonw_executable(str(python)), pythonw)

    def test_accepts_pythonw_itself(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pythonw = Path(temp_dir) / "pythonw.exe"
            pythonw.write_bytes(b"")
            with mock.patch.object(launcher.shutil, "which", return_value=None):
                self.assertEqual(launcher.pythonw_executable(str(pythonw)), pythonw)

    def test_falls_back_to_python_when_pythonw_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            python = Path(temp_dir) / "python.exe"
            python.write_bytes(b"")
            with mock.patch.object(launcher.shutil, "which", return_value=None):
                self.assertEqual(launcher.pythonw_executable(str(python)), python)

    def test_reports_when_no_interpreter_is_found(self) -> None:
        missing = Path(tempfile.gettempdir()) / "autoscrcpy-no-python.exe"
        with mock.patch.object(launcher.shutil, "which", return_value=None):
            self.assertIsNone(launcher.pythonw_executable(str(missing)))


if __name__ == "__main__":
    unittest.main()
