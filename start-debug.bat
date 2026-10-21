@echo off
setlocal
cd /d "%~dp0"
echo Starting AutoScrcpy with a visible console...
echo Close the UI window to stop the backend, or quit from the tray icon.
echo.
python app.py --verbose %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo AutoScrcpy exited with code %RC%.
  pause
)
exit /b %RC%
