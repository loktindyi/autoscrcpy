@echo off
setlocal
cd /d "%~dp0"
echo Starting AutoScrcpy with a visible console...
echo Use the top-right window button, the window close button or the tray icon to quit.
echo.
python app.py --verbose %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo AutoScrcpy exited with code %RC%.
  pause
)
exit /b %RC%
